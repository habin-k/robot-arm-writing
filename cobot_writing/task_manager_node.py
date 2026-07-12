"""로봇 글쓰기 전체 작업을 실행하는 ROS2 작업 관리자 노드.

HMI 서버가 발행한 글쓰기 웨이포인트를 받아 종이 확인, 펜 파지, 글쓰기,
펜 반납, 도장 파지, 도장 찍기, 도장 반납, 종이 배출, 원점 복귀 순서로
하나의 작업을 수행한다.

ROS 콜백은 플래그 갱신 또는 명령 큐 입력만 담당하고, 실제 Doosan 모션
명령은 TaskManager가 메인 스레드에서 실행한다. 이렇게 분리하면 DSR API
호출과 구독 콜백이 충돌하지 않고, 모션 중에도 비상정지와 조그 콜백을
백그라운드 executor에서 처리할 수 있다.
"""

from enum import Enum
import json
import queue
import threading
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy
import DR_init
from dsr_msgs2.srv import Jog, MoveStop
from onrobot_rg_msgs.msg import OnRobotRGInput
from std_msgs.msg import Bool, Float32MultiArray, String
from std_srvs.srv import Trigger

# 힘 제어 글쓰기 엔진.
from cobot_writing.writer import PenWriter

DR_init.__dsr__id = "dsr01"
DR_init.__dsr__model = "m0609"

VEL, ACC = 80, 80
ROBOT_MODE_MANUAL = 0
ROBOT_MODE_AUTONOMOUS = 1

# HMI 수동 제어용 DSR 상수.
DR_QSTOP        = 1   # 정지 모드: 1=QSTOP(급정지)
JOG_AXIS_TASK_X = 6   # 태스크 조그 축 X. +axis_idx(0~5) → X,Y,Z,RX,RY,RZ
DR_BASE_REF     = 0   # 조그 기준 좌표 = BASE

# PENS 는 작업자가 선택할 수 있는 붓펜별 설정 테이블이다.
# key(red/purple/cyan)는 /robot/pen 토픽으로 들어오는 펜 이름과 반드시 일치해야 한다.
# x, y:
#   BASE 좌표계 기준 펜 보관 위치(mm). grip_pen()/return_pen() 이 이 좌표로 이동한다.
# contact_force:
#   글씨를 쓸 때 PenWriter 가 종이 접촉을 판정하는 외력 임계값(N).
#   펜별 두께 차이에 맞춰 접촉 판단 힘을 다르게 둔다.
# z 좌표:
#   펜 상단 접근 높이 z=197, 파지 높이 z=108.5는 grip_pen()/return_pen() 안에서 공통으로 사용한다.
PENS = {
    'red':    {'x': 237.0,  'y': -28.0,   'contact_force': 2.4},
    'purple': {'x': 236.04, 'y': -188.02, 'contact_force': 1.8},
    'cyan':   {'x': 241.11, 'y': -105.35, 'contact_force': 1.8},
}
# 펜 선택 토픽을 받기 전의 기본값. 알 수 없는 펜 이름이 들어오면 이 기본 펜을 사용한다.
DEFAULT_PEN = 'red'


class RobotState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    MANUAL_REQUIRED = "manual_required"


class TaskStateNode(Node):
    """ROS 통신 인터페이스 노드.

    구독 콜백은 공유 상태 갱신 또는 명령 큐 입력만 수행한다. 블로킹되는
    DSR 모션 명령은 메인 스레드의 TaskManager에서만 실행한다.
    """

    def __init__(self, cmd_queue, state):
        super().__init__('task_manager', namespace='dsr01')

        # 콜백과 메인 모션 루프 사이의 공유 채널.
        self.q = cmd_queue         # grip/home/reset 등 DSR 모션 명령을 넘기는 큐
        self.state = state         # {'emergency': bool, ...} — writer 와 공유(비상정지 전달)

        # HMI 실행 요청(/robot/target_moving 수신)이 들어오면 작업을 시작한다.
        self.start_task = False
        self.paper_present = None   # 종이 유무 (센서 저장용, 시작 트리거 아님)

        # 그리퍼 폭 피드백 수신 여부와 최신성을 판단하기 위한 상태.
        self.gripper_width = None
        self.gripper_width_seq = 0

        self.robot_state = RobotState.IDLE
        self.retry_requested = False

        # 비상정지용 move_stop 서비스 (진행 중 모션 즉시 중단) / 연속 조그용 jog 서비스
        self.move_stop_cli = self.create_client(MoveStop, '/dsr01/motion/move_stop')
        self.jog_cli       = self.create_client(Jog,      '/dsr01/motion/jog')

        # 서버(/robot/target_moving)가 보낸 알파벳 웨이포인트를 저장. write()에서 사용.
        self.latest_waypoints = []
        self.moving_sub = self.create_subscription(
            Float32MultiArray,
            '/robot/target_moving',
            self.moving_callback,
            10
        )

        self.paper_sub = self.create_subscription(
            Bool,
            '/paper_sensor',
            self.paper_callback,
            10
        )

        # 펜/도장을 제대로 잡았는지 확인하기 위해 OnRobot 그리퍼 폭을 계속 구독한다.
        # grip()/ungrip() 이후 gripper_width_seq 가 증가했는지 확인해 최신 폭 데이터만 판정에 쓴다.
        self.gripper_width_sub = self.create_subscription(
            OnRobotRGInput,
            '/OnRobotRGInput',
            self.gripper_width_callback,
            10
        )

        self.retry_srv = self.create_service(
            Trigger,
            '/dsr01/task_manager/retry',
            self.retry_callback
        )

        # 비상정지·조그는 즉시 서비스 호출, 블로킹 모션은 큐로 넘겨 메인 스레드에서 실행한다.
        self.create_subscription(Bool,              '/safety/emergency_stop', self._on_estop, 10)
        self.create_subscription(Bool,              '/robot/go_home',         self._on_home,  10)
        self.create_subscription(Bool,              '/robot/error_reset',     self._on_reset, 10)
        self.create_subscription(Float32MultiArray, '/robot/jog',             self._on_jog,   10)
        self.create_subscription(Bool,              '/robot/grip',            self._on_grip,  10)

        # HMI 펜 컬러 선택 (빨강/보라/청록) → run_once 에서 파지 좌표와 접촉힘을 결정한다.
        # 예: /robot/pen "purple" 수신 → selected_pen="purple" 저장 → 다음 작업부터 보라 펜 사용.
        self.selected_pen = DEFAULT_PEN
        self.create_subscription(String,            '/robot/pen',             self._on_pen,   10)

        # HMI 관리자 파라미터 설정 (글씨/공이동 속도·힘·접촉힘). 콜백은 JSON 저장만 하고
        # 실제 적용은 메인 스레드에서 한다. transient_local(latched) → 노드가 나중에 떠도
        # 서버가 마지막으로 발행한 값을 자동 수신한다 (재시작해도 설정 유지).
        self.pending_tuning = None
        tuning_qos = QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST,
                                durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(String,            '/robot/tuning',          self._on_tuning, tuning_qos)

    def paper_callback(self, msg):
        # 종이 유무만 저장한다. 시작 트리거는 HMI 시작 버튼(웨이포인트 수신)으로 옮김.
        # (종이 센서로 자동 시작하면 task_manager 켜자마자 로봇이 움직여버림)
        self.paper_present = msg.data

    def gripper_width_callback(self, msg):
        # gwdf 는 OnRobot 메시지의 그리퍼 폭 피드백값이다.
        # 코드에서는 mm 단위로 보기 위해 /10.0 변환 후 저장한다.
        self.gripper_width = msg.gwdf / 10.0
        # 파지 직후 새 피드백이 들어왔는지 구분하기 위한 순번 카운터.
        # grip()/ungrip() 호출 전 값을 저장해 두고, 이후 이 값이 증가하면 최신 데이터로 본다.
        self.gripper_width_seq += 1

    def moving_callback(self, msg):
        # 서버가 발행한 웨이포인트(flat 7값×N)를 저장하고 작업 시작을 요청한다.
        # HMI 에서 문구 입력 후 '시작(execute)' 을 누르면 이 토픽이 오고, 그때만 로봇이 움직인다.
        self.latest_waypoints = list(msg.data)
        self.state['emergency'] = False   # 새 작업 요청 → 비상정지 플래그 해제
        self.start_task = True
        self.get_logger().info(
            f"웨이포인트 수신: {len(self.latest_waypoints)//7}점 → 작업 시작 요청")

    def retry_callback(self, _req, res):
        if self.robot_state != RobotState.MANUAL_REQUIRED:
            res.success = False
            res.message = f"재시도 불가: 현재 상태={self.robot_state.value}"
            return res

        if not self.latest_waypoints:
            res.success = False
            res.message = "재시도 불가: 저장된 웨이포인트가 없습니다"
            return res

        self.retry_requested = True
        res.success = True
        res.message = "재시도 요청 수신"
        self.get_logger().info("관리자 재시도 요청 수신")
        return res

    def _on_estop(self, msg):
        # 비상정지: emergency 플래그로 진행 중 글쓰기/시퀀스 루프를 끊고,
        # move_stop 서비스로 현재 모션을 즉시 중단한다 (응답 대기 안 함).
        if msg.data:
            self.state['emergency'] = True
            req = MoveStop.Request()
            req.stop_mode = DR_QSTOP
            self.move_stop_cli.call_async(req)   # 응답 대기 없이 전송
            self.get_logger().error("비상정지 수신 — 로봇 정지 명령 전송")

    def _on_home(self, msg):
        if msg.data:
            self.q.put(('home', None))

    def _on_reset(self, msg):
        if msg.data:
            self.q.put(('reset', None))

    def _on_grip(self, msg):
        # 참=그립(집기), 거짓=언그립(놓기) — 큐로 넘겨 메인 스레드에서 실행
        self.q.put(('grip' if msg.data else 'ungrip', None))

    def _on_pen(self, msg):
        # HMI 에서 선택한 붓펜 컬러 저장.
        # 여기서는 로봇을 움직이지 않고 selected_pen 만 바꾼다.
        # 실제 펜 파지는 /robot/target_moving 수신 후 run_once() 시퀀스 안에서 수행된다.
        pen = msg.data
        if pen in PENS:
            self.selected_pen = pen
            self.get_logger().info(f"펜 선택: {pen}")
        else:
            # 등록되지 않은 펜 이름은 무시하고 현재 선택을 유지한다.
            self.get_logger().warn(f"알 수 없는 펜: {pen} (무시)")

    def _on_tuning(self, msg):
        # HMI 관리자 파라미터 설정 → JSON 파싱해서 저장만. 실제 적용은 메인 루프에서.
        try:
            self.pending_tuning = json.loads(msg.data)
            self.get_logger().info(f"모션 파라미터 수신: {self.pending_tuning}")
        except Exception as e:
            self.get_logger().warn(f"모션 파라미터 파싱 실패: {e}")

    def _on_jog(self, msg):
        # 연속 조그: [axis_idx(0~5), speed_signed]. speed!=0 이동 시작, 0 정지.
        if len(msg.data) < 2:
            return
        axis_idx = int(msg.data[0])
        speed    = float(msg.data[1])
        req = Jog.Request()
        req.jog_axis       = JOG_AXIS_TASK_X + axis_idx
        req.move_reference = DR_BASE_REF
        req.speed          = speed
        self.jog_cli.call_async(req)  # 응답 대기 없이 전송


class TaskManager:
    """하나의 글쓰기 작업에 필요한 모든 블로킹 로봇 모션을 실행한다."""

    def __init__(self, node, state):
        self.node = node
        # 비상정지 등 공유 상태 (TaskStateNode·PenWriter 와 같은 dict 를 공유).
        self.state = state

        from DSR_ROBOT2 import (
            movej,
            movel,
            wait,
            set_digital_output,
            set_tool,
            set_tcp,
            task_compliance_ctrl,
            set_desired_force,
            release_compliance_ctrl,
            release_force,
            set_robot_mode,
            DR_FC_MOD_REL,
            DR_MV_MOD_REL,
            DR_BASE,
        )

        from DR_common2 import posj, posx

        self.movej = movej
        self.movel = movel
        self.wait = wait
        self.set_digital_output = set_digital_output
        self.set_tool = set_tool
        self.set_tcp = set_tcp
        self.task_compliance_ctrl = task_compliance_ctrl
        self.set_desired_force = set_desired_force
        self.release_compliance_ctrl = release_compliance_ctrl
        self.release_force = release_force
        self.set_robot_mode = set_robot_mode
        self.DR_FC_MOD_REL = DR_FC_MOD_REL
        self.DR_MV_MOD_REL = DR_MV_MOD_REL
        self.DR_BASE = DR_BASE
        self.posj = posj
        self.posx = posx

        # Tool/TCP와 로봇 모드는 TaskManager가 관리하고, writer는 글쓰기 구간만 담당한다.
        self.writer = PenWriter(node, self.state, init_robot=False)

    def _check_estop(self):
        """비상정지가 요청되면 현재 시퀀스를 중단한다."""
        if self.state.get('emergency'):
            raise RuntimeError("비상정지로 작업 중단")

    def grip(self):
        """OnRobot 그리퍼를 닫고 최신 폭 피드백을 기다린다."""
        self.node.get_logger().info("그리퍼 닫기")
        self.drain_gripper_callbacks(0.2)
        before_seq = self.node.gripper_width_seq
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(1, 1)
        self.wait(1)
        self.wait_for_gripper_update(before_seq)

    def ungrip(self):
        """OnRobot 그리퍼를 열고 최신 폭 피드백을 기다린다."""
        self.node.get_logger().info("그리퍼 열기")
        self.drain_gripper_callbacks(0.2)
        before_seq = self.node.gripper_width_seq
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(2, 1)
        self.wait(1)
        self.wait_for_gripper_update(before_seq)

    def drain_gripper_callbacks(self, duration_sec=0.2):
        """백그라운드 executor가 그리퍼 폭 콜백을 반영할 시간을 준다."""
        time.sleep(duration_sec)

    def wait_for_gripper_update(self, previous_seq, timeout_sec=10.0, settle_sec=0.2):
        """그리퍼 명령 이후 /OnRobotRGInput 새 메시지가 들어올 때까지 기다린다."""
        deadline = time.monotonic() + timeout_sec
        while rclpy.ok() and time.monotonic() < deadline:
            if self.node.gripper_width_seq > previous_seq:
                time.sleep(settle_sec)
                return True
            time.sleep(0.05)
        self.node.get_logger().warn("그리퍼 최신 데이터 수신 대기 시간 초과")
        return False

    def grip_pen(self, pen=DEFAULT_PEN):
        """선택된 펜 보관 위치로 이동해 펜을 집는다."""
        p = PENS.get(pen, PENS[DEFAULT_PEN])
        x, y = p['x'], p['y']
        self.node.get_logger().info(f"펜 파지 ({pen}) x={x} y={y}")
        self.movel(self.posx(x, y, 197, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(x, y, 108.5, 90, 180, 90), vel=VEL, acc=ACC)
        self.grip()
        self.wait(0.5)
        self.movel(self.posx(x, y, 197, 90, 180, 0), vel=VEL, acc=ACC)

    def write(self):
        """서버가 발행한 웨이포인트를 PenWriter로 실행한다."""
        wps = self.node.latest_waypoints
        if not wps:
            raise RuntimeError("그릴 웨이포인트 없음 (/robot/target_moving 미수신)")
        self.node.get_logger().info(f"글쓰기 시작 (웨이포인트 {len(wps)//7}점)")
        self.writer.draw(wps)

    def return_pen(self, pen=DEFAULT_PEN):
        """사용한 펜을 원래 보관 위치에 내려놓는다."""
        p = PENS.get(pen, PENS[DEFAULT_PEN])
        x, y = p['x'], p['y']
        self.node.get_logger().info(f"펜 복귀 ({pen})")
        self.movel(self.posx(0, 0, 20, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.movel(self.posx(x, y, 197, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(x, y, 108.5, 90, 180, 90), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.ungrip()

    def grip_stamp(self):
        """도장 보관 위치로 이동해 도장을 집는다."""
        self.node.get_logger().info("도장 파지")
        self.movel(self.posx(0, 0, 90, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.movel(self.posx(242, 72, 197, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(242, 72, 33.02, 90, 180, 90), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.grip()

    def stamp(self):
        """지정된 위치에 도장을 찍는다."""
        self.node.get_logger().info("도장 찍기")
        self.movel(self.posx(0, 0, 120, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.movel(self.posx(527, 99, 150, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(527, 99, 78, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(527, 99, 150, 90, 180, 90), vel=VEL, acc=ACC)

    def return_stamp(self):
        """도장을 원래 보관 위치에 내려놓는다."""
        self.node.get_logger().info("도장 복귀")
        self.movel(self.posx(527, 99, 150, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(242, 72, 150, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(242, 72, 28, 90, 180, 90), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.ungrip()

    def is_gripped(self, label):
        """그리퍼 폭 피드백으로 펜/도장 파지 성공 여부를 확인한다."""
        self.drain_gripper_callbacks(0.2)
        width = self.node.gripper_width

        if width is None:
            raise RuntimeError(f"그리퍼 데이터 수신 실패")

        if width < 10:
            raise RuntimeError(f"{label} 파지 실패 width={width:.2f}")

        self.node.get_logger().info(f"파지 확인: width={width:.2f}")
        return True

    def grip_with_retry(self, label, grip_fn, max_retries=1):
        """파지 모션을 실행하고 실패 시 정해진 횟수만큼 재시도한다."""
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    self.node.get_logger().warn(
                        f"{label} 파지 재시도 {attempt}/{max_retries}"
                    )
                    self.ungrip()
                    self.wait(0.5)

                self._check_estop()
                grip_fn()
                self._check_estop()
                self.is_gripped(label)
                return True

            except Exception as e:
                if self.state.get('emergency'):
                    raise
                last_error = e
                self.node.get_logger().warn(
                    f"{label} 파지 확인 실패: {e}"
                )

        raise RuntimeError(f"{label} 파지 최종 실패: {last_error}")

    def eject_paper(self):
        """순응 제어와 미세 힘 제어로 종이 더미에서 한 장을 일부 빼낸다."""
        fd = [0, 0, -0.5, 0, 0, 0]
        fctrl_dir = [0, 0, 1, 0, 0, 0]

        self.node.get_logger().info("종이 배출 시작")
        self.movel(self.posx(0, 0, 120, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.movel(self.posx(462, 80, 120, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(462, 80, 62, 90, 180, 90), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.task_compliance_ctrl([2000, 2000, 2000, 200, 200, 200])
        self.wait(1)
        self.set_desired_force(fd, fctrl_dir, mod=self.DR_FC_MOD_REL)
        self.wait(3)
        self.movel(self.posx(0, -40, 0, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.wait(0.5)
        self.release_force()
        self.wait(0.5)
        self.release_compliance_ctrl()
        self.wait(0.5)
        self.node.get_logger().info("종이 배출 완료")

    def grip_paper(self):
        """일부 빠져나온 종이를 집어 배출 위치로 옮긴다."""
        self.node.get_logger().info('종이 집기 배출 모션 시작')
        self.movel(self.posx(462, 60, 85, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -180, 85, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -160, 85, 90, 100, 0), vel=VEL, acc=ACC)
        self.grip()
        self.movel(self.posx(462, -160, 85, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -160, 360, 160, 180, 70), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -50, 360, 170, -180, 77.62), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -50, 360, 270, -180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(664, -50, 138, 270, -180, 90), vel=VEL, acc=ACC)
        self.movej(self.posj(0, 0, 0, 0, -30, 0), vel=25, acc=25, mod=self.DR_MV_MOD_REL)
        self.ungrip()
        self.node.get_logger().info('종이 집기 배출 모션 완료')

    def paper_ready(self):
        """종이 센서가 종이 있음 상태를 보고했는지 확인한다."""
        if self.node.paper_present:
            return True
        return False

    def go_home(self):
        self.node.get_logger().info("원점으로 이동중")
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)

    def enter_manual_recovery_mode(self):
        self.node.get_logger().warn("수동 복구 모드 전환 시작")
        self.state['emergency'] = True

        try:
            self.release_force()
        except Exception as e:
            self.node.get_logger().warn(f"힘 제어 해제 실패 또는 불필요: {e}")

        try:
            self.release_compliance_ctrl()
        except Exception as e:
            self.node.get_logger().warn(f"컴플라이언스 해제 실패 또는 불필요: {e}")

        try:
            ret = self.set_robot_mode(ROBOT_MODE_MANUAL)
            if ret != 0:
                raise RuntimeError(f"set_robot_mode 반환값={ret}")
            self.node.get_logger().warn("로봇 MANUAL 모드 전환 완료")
        except Exception as e:
            self.node.get_logger().error(f"MANUAL 모드 전환 실패: {e}")

        # HMI 수동 복구 팝업 트리거용 상태 발행 (서버 STATUS_MAP 이 manual_required 로 매핑).
        try:
            self.writer.publish_status("MANUAL_REQUIRED")
        except Exception as e:
            self.node.get_logger().warn(f"MANUAL_REQUIRED 상태 발행 실패: {e}")
        self.node.robot_state = RobotState.MANUAL_REQUIRED

    def enter_autonomous_mode(self):
        self.node.get_logger().info("AUTONOMOUS 모드 전환 시작")
        self.state['emergency'] = False
        ret = self.set_robot_mode(ROBOT_MODE_AUTONOMOUS)
        if ret != 0:
            raise RuntimeError(f"AUTONOMOUS 모드 전환 실패: set_robot_mode 반환값={ret}")
        self.set_tool("Tool Weight")
        self.set_tcp("GripperDA_v1")
        self.node.get_logger().info("로봇 AUTONOMOUS 모드 전환 완료")

    def handle_command(self, cmd, data=None):
        """TaskStateNode 콜백이 큐에 넣은 수동 제어 명령을 메인 스레드에서 실행한다.
        (grip/ungrip=그리퍼, home=원점, reset=에러리셋)"""
        self.state['busy'] = True
        try:
            if cmd == 'grip':
                self.grip()
            elif cmd == 'ungrip':
                self.ungrip()
            elif cmd == 'home':
                self.node.get_logger().info("[HMI] 원점 복귀")
                self.go_home()
            elif cmd == 'reset':
                self.do_reset()
        except Exception as e:
            self.node.get_logger().error(f"수동 명령 '{cmd}' 실행 실패: {e}")
        finally:
            self.state['busy'] = False

    def apply_tuning(self, params):
        """HMI 관리자 파라미터 설정 반영: 모션 파라미터(writer) + 펜별 접촉힘(PENS).
        메인 스레드에서만 호출된다 (DSR 호출 없이 인스턴스 변수만 교체)."""
        # 글씨/공이동 속도·가속, 붓 누르는 힘, 힘제어 높이 → writer 인스턴스 변수
        self.writer.apply_tuning(params)
        # 펜별 접촉 판단 힘 → PENS 갱신 (다음 run_once 의 set_contact_force 에 반영)
        cf = params.get('contact_force')
        if isinstance(cf, dict):
            for pen, val in cf.items():
                if pen in PENS:
                    try:
                        PENS[pen]['contact_force'] = float(val)
                    except (TypeError, ValueError):
                        self.node.get_logger().warn(f"접촉힘 값 무시: {pen}={val}")
            self.node.get_logger().info(
                f"펜별 접촉힘 갱신: " +
                ", ".join(f"{p}={PENS[p]['contact_force']}" for p in PENS))

    def do_reset(self):
        """에러 리셋: 자율 모드 복귀 + 비상정지 플래그 해제 + IDLE 로 복귀."""
        self.node.get_logger().info("[HMI] 에러 리셋")
        self.enter_autonomous_mode()
        self.node.robot_state = RobotState.IDLE
        self.writer.publish_status("IDLE")

    def run_once(self):
        """펜 파지부터 종이 배출까지 하나의 전체 작업을 실행한다."""
        try:
            self.state['emergency'] = False
            self.writer.publish_status("WRITING")
            self.set_tool("Tool Weight")
            self.set_tcp("GripperDA_v1")
            self.go_home()
            self.ungrip()

            # 1. 선택된 펜으로 글씨를 쓴다.
            pen = self.node.selected_pen
            self.writer.set_contact_force(PENS.get(pen, PENS[DEFAULT_PEN])['contact_force'])
            self.node.get_logger().info(f"이번 작업 펜: {pen}")
            self.grip_with_retry("펜", lambda: self.grip_pen(pen), max_retries=1)
            self._check_estop()
            self.write()
            # 글쓰기 뒤에도 도장/배출이 이어지므로 작업 상태를 WRITING으로 유지한다.
            self.writer.publish_status("WRITING")
            self._check_estop()
            self.return_pen(pen)
            self._check_estop()

            # 2. 도장을 찍고 원위치에 반납한다.
            self.grip_with_retry("도장", self.grip_stamp, max_retries=1)
            self._check_estop()
            self.stamp()
            self._check_estop()
            self.return_stamp()
            self._check_estop()

            # 3. 완성된 종이를 배출한다.
            self.eject_paper()
            self.grip_paper()
            self.go_home()
            self.node.robot_state = RobotState.IDLE
            self.writer.publish_status("IDLE")

        except Exception as e:
            self.node.get_logger().error(f"작업 중단: {e}")
            self.node.get_logger().error("관리자 수동 복구 모드로 진입합니다. Reset 필요.")
            self.enter_manual_recovery_mode()


def main(args=None):
    rclpy.init(args=args)

    # 콜백(구독 노드)↔메인 스레드(모션) 공유 채널
    cmd_queue = queue.Queue()
    state = {'emergency': False, 'busy': False}

    # 1) DSR 전용 노드 — DSR 모션 함수가 내부적으로만 spin 한다 (우리가 spin 하지 않음).
    dsr_node = rclpy.create_node('dsr_motion', namespace='dsr01')
    DR_init.__dsr__id    = "dsr01"
    DR_init.__dsr__model = "m0609"
    DR_init.__dsr__node  = dsr_node

    # 2) 명령/상태 구독 노드 — 전용 executor 로 백그라운드 스레드에서 spin.
    #    (글쓰기/집기 모션이 메인 스레드를 블로킹하는 중에도 비상정지·그립·조그 콜백이
    #     실시간으로 처리되게 하려면 반드시 별도 스레드에서 spin 해야 한다.)
    node = TaskStateNode(cmd_queue, state)
    sub_exec = SingleThreadedExecutor()
    sub_exec.add_node(node)
    threading.Thread(target=sub_exec.spin, daemon=True).start()

    # 3) 메인 스레드에서 시퀀서 실행 (DSR 함수는 여기서만 호출)
    sequencer = TaskManager(node, state)
    sequencer.set_tool("Tool Weight")
    time.sleep(1)
    sequencer.set_tcp("GripperDA_v1")
    time.sleep(1)
    node.get_logger().info("task_manager 시작 (HMI 제어 연동)")

    try:
        while rclpy.ok():
            # 3-0) HMI 파라미터 설정 반영 (콜백이 저장한 값을 메인 스레드에서 적용 — DSR 호출 없음)
            if node.pending_tuning is not None:
                params = node.pending_tuning
                node.pending_tuning = None
                sequencer.apply_tuning(params)

            # 3-1) HMI 수동 제어 명령 우선 처리 (grip/ungrip/home/reset)
            try:
                cmd, data = cmd_queue.get_nowait()
            except queue.Empty:
                cmd = None
            if cmd is not None:
                sequencer.handle_command(cmd, data)

            # 3-2) 글쓰기 자동 시퀀스 (HMI 시작 버튼 → 웨이포인트 수신)
            elif node.start_task and node.robot_state == RobotState.IDLE:
                node.start_task = False
                # 종이가 없으면 작업을 시작하지 않고 HMI 에 '종이 없음' 을 알린다 (IDLE 유지).
                if not sequencer.paper_ready():
                    node.get_logger().warn("종이가 감지되지 않아 작업을 시작하지 않습니다.")
                    sequencer.writer.publish_no_paper()
                else:
                    node.robot_state = RobotState.RUNNING
                    sequencer.run_once()

            # 3-3) 수동 복구 후 재시도 서비스 요청: 자동 모드 전환 후 같은 웨이포인트로 재실행
            elif node.retry_requested and node.robot_state == RobotState.MANUAL_REQUIRED:
                node.retry_requested = False
                # 재시도도 종이가 있어야 시작 (없으면 MANUAL_REQUIRED 유지 → 다시 재시도 가능).
                if not sequencer.paper_ready():
                    node.get_logger().warn("종이가 감지되지 않아 재시도를 시작하지 않습니다.")
                    sequencer.writer.publish_no_paper()
                    continue
                node.get_logger().info("관리자 수동 복구 후 작업 재시도 시작")
                try:
                    sequencer.enter_autonomous_mode()
                    node.robot_state = RobotState.RUNNING
                    sequencer.run_once()
                except Exception as e:
                    node.get_logger().error(f"재시도 시작 실패: {e}")
                    sequencer.enter_manual_recovery_mode()

            # 3-4) 현재 좌표·외력을 HMI 로 발행 (조그 중에도 갱신됨)
            else:
                sequencer.writer.publish_live()
                time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        dsr_node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()

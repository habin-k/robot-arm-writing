import queue
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import Bool, Float32MultiArray
from onrobot_rg_msgs.msg import OnRobotRGInput
from dsr_msgs2.srv import MoveStop, Jog
import DR_init
from enum import Enum

# 그리기 엔진 (pub_sub 힘제어 로직 분리본). 같은 패키지의 writer.py.
from cobot_writing.writer import PenWriter
# 종이 배출 모션 엔진 (paper_ejector_node.py 를 클래스화한 것).
from cobot_writing.paper_ejector_node import PaperEjector
# 1. 초기화 변수 선언
DR_init.__dsr__id = "dsr01"
DR_init.__dsr__model = "m0609"

VEL, ACC = 50, 50

# HMI 제어(비상정지/조그)용 상수 — pub_sub.py 와 동일하게 유지.
DR_QSTOP        = 1   # 정지 모드: 1=QSTOP(급정지)
JOG_AXIS_TASK_X = 6   # 태스크 조그 축 X. +axis_idx(0~5) → X,Y,Z,RX,RY,RZ
DR_BASE_REF     = 0   # 조그 기준 좌표 = BASE

class RobotState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    MANUAL_REQUIRED = "manual_required"

# 2. ROS 2 통신을 담당할 클래스 정의
#    구독 콜백은 '플래그 설정' 또는 '명령 큐에 넣기'만 하고, 실제 DSR 모션은
#    메인 스레드(TaskManager)에서 실행한다. 이 노드는 백그라운드 executor 로 spin 되므로
#    (main() 참고) 글쓰기/집기 모션이 메인 스레드를 블로킹하는 중에도 비상정지·그립·조그
#    콜백이 실시간으로 처리된다.
class TaskStateNode(Node):
    def __init__(self, cmd_queue, state):
        super().__init__('task_manager', namespace='dsr01')

        # 콜백↔메인스레드 공유 채널
        self.q = cmd_queue         # grip/home/reset 등 DSR 모션 명령을 넘기는 큐
        self.state = state         # {'emergency': bool, ...} — writer 와 공유(비상정지 전달)

        # 상태를 공유할 플래그 변수
        # start_task: 작업 시작 요청. HMI 시작 버튼(=/robot/target_moving 웨이포인트 도착)으로만 True.
        self.start_task = False
        self.paper_present = None   # 종이 유무 (센서 저장용, 시작 트리거 아님)
        self.gripper_width = 0.0
        # 최신 그리퍼 값 확인용 None 초기화 / 시퀀스 추가
        self.gripper_width = None
        self.gripper_width_seq = 0

        self.robot_state = RobotState.IDLE

        # 그리퍼 파지 검사 우회 플래그 (임시 테스트용).
        #   True  = 정상 (is_gripped 로 펜/도장 파지 확인)
        #   False = 우회 (/OnRobotRGInput 발행 노드 없을 때 그리기만 테스트)
        # 실행 시: ros2 run cobot_writing task_manager --ros-args -p check_grip:=false
        self.check_grip = self.declare_parameter('check_grip', True).value
        if not self.check_grip:
            self.get_logger().warn("⚠ check_grip=False — 펜/도장 파지 검사 우회 (테스트 모드)")

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

        self.gripper_width_sub = self.create_subscription(
            OnRobotRGInput,
            '/OnRobotRGInput',
            self.gripper_width_callback,
            10
        )

        # ── HMI 관리자 제어 버튼 구독 (pub_sub.py 와 동일 토픽) ──────────────
        #   비상정지·조그는 콜백에서 서비스 직접 호출(fire-and-forget),
        #   그립/언그립·원점·에러리셋은 DSR 모션이 필요하므로 큐로 넘겨 메인 스레드에서 실행.
        self.create_subscription(Bool,              '/safety/emergency_stop', self._on_estop, 10)
        self.create_subscription(Bool,              '/robot/go_home',         self._on_home,  10)
        self.create_subscription(Bool,              '/robot/error_reset',     self._on_reset, 10)
        self.create_subscription(Float32MultiArray, '/robot/jog',             self._on_jog,   10)
        self.create_subscription(Bool,              '/robot/grip',            self._on_grip,  10)

    def paper_callback(self, msg):
        # 종이 유무만 저장한다. 시작 트리거는 HMI 시작 버튼(웨이포인트 수신)으로 옮김.
        # (종이 센서로 자동 시작하면 task_manager 켜자마자 로봇이 움직여버림)
        self.paper_present = msg.data

    def gripper_width_callback(self, msg):
        # self.get_logger().info(f"그리퍼 너비 수신: {msg.gwdf / 10.0}")
        self.gripper_width = msg.gwdf / 10.0
        # 그리퍼 메시지 갱신 여부 추가
        self.gripper_width_seq += 1

    def moving_callback(self, msg):
        # 서버가 발행한 웨이포인트(flat 7값×N)를 저장하고 작업 시작을 요청한다.
        # HMI 에서 문구 입력 후 '시작(execute)' 을 누르면 이 토픽이 오고, 그때만 로봇이 움직인다.
        self.latest_waypoints = list(msg.data)
        self.state['emergency'] = False   # 새 작업 요청 → 비상정지 플래그 해제
        self.start_task = True
        self.get_logger().info(
            f"웨이포인트 수신: {len(self.latest_waypoints)//7}점 → 작업 시작 요청")

    # ── HMI 제어 콜백 ─────────────────────────────────────────────────────────
    def _on_estop(self, msg):
        # 비상정지: emergency 플래그로 진행 중 글쓰기/시퀀스 루프를 끊고,
        # move_stop 서비스로 현재 모션을 즉시 중단한다 (응답 대기 안 함).
        if msg.data:
            self.state['emergency'] = True
            req = MoveStop.Request()
            req.stop_mode = DR_QSTOP
            self.move_stop_cli.call_async(req)   # fire-and-forget
            self.get_logger().error("비상정지 수신 — 로봇 정지 명령 전송")

    def _on_home(self, msg):
        if msg.data:
            self.q.put(('home', None))

    def _on_reset(self, msg):
        if msg.data:
            self.q.put(('reset', None))

    def _on_grip(self, msg):
        # True=그립(집기), False=언그립(놓기) — 큐로 넘겨 메인 스레드에서 실행
        self.q.put(('grip' if msg.data else 'ungrip', None))

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
        self.jog_cli.call_async(req)  # fire-and-forget


class TaskManager:
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
        DR_FC_MOD_ABS,
        DR_FC_MOD_REL,
        DR_MV_MOD_ABS,
        DR_MV_MOD_REL,
        DR_BASE,
        DR_TOOL,
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

        self.DR_FC_MOD_ABS = DR_FC_MOD_ABS
        self.DR_FC_MOD_REL = DR_FC_MOD_REL
        self.DR_MV_MOD_ABS = DR_MV_MOD_ABS
        self.DR_MV_MOD_REL = DR_MV_MOD_REL
        self.DR_BASE = DR_BASE
        self.DR_TOOL = DR_TOOL

        self.posj = posj
        self.posx = posx

        # 그리기 엔진 (pub_sub 힘제어 로직). init_robot=False:
        #   tool/tcp/자율모드는 task_manager 가 관리하고, 좌표 기준(User_102)은
        #   writer 가 draw() 안에서만 바꿨다가 BASE 로 되돌린다.
        # state['emergency'] 로 비상정지를 전달 (HMI 비상정지 버튼 → TaskStateNode._on_estop).
        self.writer = PenWriter(node, self.state, init_robot=False)

        # 종이 배출 엔진. tool/tcp 는 task_manager 가 관리하므로 init_robot=False.
        self.paper_ejector = PaperEjector(node, init_robot=False)

    # 비상정지가 걸렸으면 예외를 던져 시퀀스를 중단한다 (run_once 의 except → MANUAL_REQUIRED).
    def _check_estop(self):
        if self.state.get('emergency'):
            raise RuntimeError("비상정지로 작업 중단")

    #—————————단위 동작 함수들———————————
    def grip(self):
        self.node.get_logger().info("그리퍼 닫기")
        # 그리퍼 명령 전 콜백 큐를 비우려고 추가했었음
        self.drain_gripper_callbacks(0.2)
        before_seq = self.node.gripper_width_seq
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(1, 1)
        self.wait(1)
        # 그리퍼 명령 후 새 width 메시지를 기다리려고 추가했었음
        self.wait_for_gripper_update(before_seq)

    def ungrip(self):
        self.node.get_logger().info("그리퍼 열기")
        # 그리퍼 명령 전 콜백 큐를 비우기 위함
        self.drain_gripper_callbacks(0.2)
        before_seq = self.node.gripper_width_seq
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(2, 1)
        self.wait(1)
        # 그리퍼 명령 후 새 width 메시지를 기다리기 위함
        self.wait_for_gripper_update(before_seq)

    # 그리퍼 width(/OnRobotRGInput) 콜백이 반영될 시간을 잠깐 준다.
    # (구독 노드를 백그라운드 executor 가 spin 하므로 여기선 대기만 하면 된다.)
    def drain_gripper_callbacks(self, duration_sec=0.2):
        time.sleep(duration_sec)

    # 그리퍼 명령 이후 최신 width 메시지가 올 때까지 기다린다 (백그라운드 spin 이 seq 를 갱신).
    def wait_for_gripper_update(self, previous_seq, timeout_sec=2.0, settle_sec=0.2):
        deadline = time.monotonic() + timeout_sec
        while rclpy.ok() and time.monotonic() < deadline:
            if self.node.gripper_width_seq > previous_seq:
                time.sleep(settle_sec)
                return True
            time.sleep(0.05)
        self.node.get_logger().warn("그리퍼 최신 데이터 수신 대기 시간 초과")
        return False

    def grip_pen(self):
        self.node.get_logger().info("펜 파지")
        # self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
        self.movel(self.posx(237, -28, 197, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(237, -28, 108.5, 90, 180, 0), vel=VEL, acc=ACC)  #mod=self.DR_MV_MOD_REL, ref=self.DR_BASE
        self.grip()
        self.wait(0.5)
        self.movel(self.posx(0, 0, 80, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        return True

    def write(self):
        # 서버가 보낸 웨이포인트로 알파벳을 그린다. 웨이포인트가 없으면 예외 →
        # run_once 의 except 로 잡혀 MANUAL_REQUIRED(관리자 수동 복구) 진입.
        wps = self.node.latest_waypoints
        if not wps:
            raise RuntimeError("그릴 웨이포인트 없음 (/robot/target_moving 미수신)")
        self.node.get_logger().info(f"글쓰기 시작 (웨이포인트 {len(wps)//7}점)")
        self.writer.draw(wps)

    def return_pen(self):
        self.node.get_logger().info("펜 복귀")
        self.movel(self.posx(0, 0, 80, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.movel(self.posx(237, -28, 197, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(237, -28, 108.5, 90, 180, 0), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.ungrip()
        return True

    def grip_stamp(self):
        self.node.get_logger().info("도장 파지")
        self.movel(self.posx(0, 0, 80, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.movel(self.posx(242, 72, 150, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(242, 72, 33.02, 90, 180, 0), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.grip()
        return True

    def stamp(self):
        # fd = [0, 0, -20, 0, 0, 0]
        # fctrl_dir = [0, 0, 1, 0, 0, 0]

        self.node.get_logger().info("도장 찍기")
        self.movel(self.posx(0, 0, 100, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.movel(self.posx(527, 99, 130, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(527, 99, 78, 90, 180, 0), vel=VEL, acc=ACC)
        # self.wait(0.5)
        # self.task_compliance_ctrl([2000, 2000, 500, 200, 200, 200])
        # self.wait(1)
        # self.set_desired_force(fd, fctrl_dir, mod=self.DR_FC_MOD_REL)
        # self.wait(1)
        # self.release_force()
        # self.wait(0.5)
        # self.release_compliance_ctrl()
        # self.wait(0.5)
        self.movel(self.posx(527, 99, 100, 90, 180, 0), vel=VEL, acc=ACC)
        return True

    def return_stamp(self):
        # fd = [0, 0, -20, 0, 0, 0]
        # fctrl_dir = [0, 0, 1, 0, 0, 0]

        self.node.get_logger().info("도장 복귀")
        self.movel(self.posx(527, 99, 130, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(242, 72, 130, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(242, 72, 28, 90, 180, 0), vel=VEL, acc=ACC)
        # self.wait(0.5)
        # self.task_compliance_ctrl([2000, 2000, 500, 200, 200, 200])
        # self.wait(1)
        # self.set_desired_force(fd, fctrl_dir, mod=self.DR_FC_MOD_REL)
        # self.wait(1)
        # self.release_force()
        # self.wait(0.5)
        # self.release_compliance_ctrl()
        self.wait(0.5)
        self.ungrip()
        return True

    def is_gripped(self, label):
        # 우회 모드(check_grip=False): 그리퍼 폭 피드백(/OnRobotRGInput) 없이 테스트할 때
        # 파지 확인을 건너뛴다. (펜/도장 감지가 필요하면 check_grip=True 로 실행)
        if not self.node.check_grip:
            self.node.get_logger().warn(f"[우회] {label} 파지 검사 건너뜀 (check_grip=False)")
            return True

        # 판정 직전에 콜백을 처리해 최신 width를 읽으려고 추가했었음
        self.drain_gripper_callbacks(0.2)
        width = self.node.gripper_width

        if width is None:
            raise RuntimeError(f"그리퍼 데이터 수신 실패")

        if width < 10:
            raise RuntimeError(f"{label} 파지 실패 width={width:.2f}")

        self.node.get_logger().info(f"파지 확인: width={width:.2f}")
        return True

    def eject_paper(self):              # 이 부분 계속 테스트 해봐야함
        fd = [0, 0, -0.5, 0, 0, 0]      # 힘도 얼마나 줄지 계속 테스트 해봐야함
        fctrl_dir = [0, 0, 1, 0, 0, 0]

        self.node.get_logger().info("종이 배출 테스트 시작")
        self.movel(self.posx(0, 0, 100, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.movel(self.posx(462, 80, 100, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(462, 80, 63, 90, 180, 90), vel=VEL, acc=ACC)     # ㅋ좌표 계속 변하는 문제점
        self.wait(0.5)
        self.task_compliance_ctrl([2000, 2000, 2000, 200, 200, 200])
        self.wait(1)
        self.set_desired_force(fd, fctrl_dir, mod=self.DR_FC_MOD_REL)
        self.wait(4)
        self.movel(self.posx(0, -80, 0, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.wait(0.5)
        self.release_force()
        self.wait(0.5)
        self.release_compliance_ctrl()
        self.wait(0.5)
        # self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
        self.node.get_logger().info("종이 배출 완료")
        return True

    def paper_grip(self):
        # paper_ejector_node.py(PaperEjector)의 종이 배출 모션을 실행한다.
        self.node.get_logger().info("종이 집어 배출 (paper_ejector)")
        self.paper_ejector.eject()
        return True

    def go_home(self):
        self.node.get_logger().info("원점으로 이동중")
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)

    def reset(self):
        pass

    # ── HMI 수동 제어 명령 처리 (메인 스레드에서 호출) ─────────────────────────
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

    def do_reset(self):
        """에러 리셋: 자율 모드 복귀 + 비상정지 플래그 해제 + IDLE 로 복귀."""
        self.node.get_logger().info("[HMI] 에러 리셋")
        from DSR_ROBOT2 import set_robot_mode
        from DRFC import ROBOT_MODE_AUTONOMOUS
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
        # 모드 전환으로 풀린 툴/TCP 재적용
        self.set_tool("Tool Weight")
        self.set_tcp("GripperDA_v1")
        self.state['emergency'] = False
        self.node.robot_state = RobotState.IDLE
        self.writer.publish_status("IDLE")

    def run_once(self):
        try:
            # 새 작업 시작 — 이전 비상정지 플래그 초기화
            self.state['emergency'] = False
            # 모드 전환 등으로 풀렸을 수 있는 툴/TCP 를 매 작업 시작 시 재적용.
            self.set_tool("Tool Weight")
            self.set_tcp("GripperDA_v1")

            self.go_home()
            self.ungrip()
            self.grip_pen()
            self.is_gripped("펜")
            self._check_estop()

            self.write()
            self._check_estop()

            self.return_pen()
            self._check_estop()

            self.grip_stamp()
            self.is_gripped("도장")
            self._check_estop()
            self.stamp()
            self._check_estop()
            self.return_stamp()
            self._check_estop()

            self.eject_paper()
            self.paper_grip()
            self.go_home()
            self.node.robot_state = RobotState.IDLE

        except Exception as e:
            self.node.get_logger().error(f"작업 중단: {e}")
            self.node.get_logger().error("관리자 수동 복구 모드로 진입합니다. Reset 필요.")
            self.node.robot_state = RobotState.MANUAL_REQUIRED # 관리자 수동 모드 진입 # RobotState 클래스 정의 시 구현


        finally:
            pass



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
    sequencer.set_tcp("GripperDA_v1")

    node.get_logger().info("task_manager 시작 (HMI 제어 연동)")

    try:
        while rclpy.ok():
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
                node.robot_state = RobotState.RUNNING
                sequencer.run_once()

            # 3-3) 유휴: 현재 좌표·외력을 HMI 로 발행 (조그 중에도 갱신됨)
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

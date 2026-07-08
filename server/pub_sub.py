import queue
import threading

import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String, Bool, Float32MultiArray
from dsr_msgs2.srv import MoveStop, Jog
import DR_init

# 정지 모드 (DSR): 0=QSTOP_STO, 1=QSTOP(급정지), 2=SSTOP(감속정지)
DR_QSTOP = 1

# 조그 축 (DSR): 태스크 좌표 X~RZ = 6~11, 기준 좌표 DR_BASE = 0
JOG_AXIS_TASK_X = 6   # +axis_idx(0~5) → X,Y,Z,RX,RY,RZ
DR_BASE_REF     = 0

ROBOT_ID    = "dsr01"
ROBOT_MODEL = "m0609"

HOME_JOINT = [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]

# ── 힘 제어 글씨 쓰기 설정 (test1.py 에서 이식) ────────────────────────────
# pen_down 획은 위치 제어로 딱딱하게 내려찍지 않고, 표면 살짝 위에서 접근한 뒤
# 순응 제어 + 목표 힘(-3N)으로 붓을 눌러 일정한 힘을 유지하며 그린다.
WRITE_FORCE_Z    = -3.0                          # 목표 힘 (N), 음수 = 아래 방향
WRITE_FORCE_DIR  = [0, 0, 1, 0, 0, 0]            # Z축 방향
WRITE_STIFFNESS  = [3000, 3000, 300, 200, 200, 200]  # X/Y 강성 높게, Z 낮게
WRITE_Z_BIAS     = 3.0                           # 표면보다 위쪽 접근 높이 (mm)
HOVER_HEIGHT     = 30.0                           # 공이동 hover 높이 (mm)

WRITE_VEL  = [20.0, 20.0]    # 글씨 쓰기 (느림)
WRITE_ACC  = [40.0, 40.0]
TRAVEL_VEL = [80.0, 60.0]    # 공이동 (빠름)
TRAVEL_ACC = [100.0, 80.0]
PROBE_VEL  = [8.0, 8.0]      # 표면 접근 (매우 느림)
PROBE_ACC  = [15.0, 15.0]

MOVESX_MAX_PTS = 50          # movesx 한 번에 넘길 수 있는 최대 포인트 수 (DSR 제한)


class SubscriberNode(Node):
    """
    구독 전용 노드. 콜백은 명령을 큐에 넣기만 하고 실제 모션은 실행하지 않는다.
    (DSR 모션 함수는 별도 DSR 노드를 내부적으로 spin하므로, 이 노드와 분리해야
     한 번만 동작하는 문제가 사라진다.)
    """

    def __init__(self, cmd_queue: queue.Queue, state: dict):
        super().__init__('controller_node', namespace=ROBOT_ID)
        self.q     = cmd_queue
        self.state = state
        self.status_pub = self.create_publisher(String, '/robot/status', 10)

        # 비상정지용 move_stop 서비스 클라이언트 (진행 중인 모션을 즉시 중단)
        self.move_stop_cli = self.create_client(MoveStop, f'/{ROBOT_ID}/motion/move_stop')
        # 연속 조그용 jog 서비스 클라이언트 (누르면 속도 지정, 떼면 속도 0)
        self.jog_cli       = self.create_client(Jog, f'/{ROBOT_ID}/motion/jog')

        self.create_subscription(Float32MultiArray, '/robot/target_moving', self._on_moving, 10)
        self.create_subscription(Bool,              '/safety/emergency_stop', self._on_estop, 10)
        self.create_subscription(Bool,              '/robot/go_home',         self._on_home, 10)
        self.create_subscription(Bool,              '/robot/error_reset',     self._on_reset, 10)
        self.create_subscription(Float32MultiArray, '/robot/jog',             self._on_jog, 10)

        self.get_logger().info("통신 노드 준비 완료")

    def _on_moving(self, msg):
        self.state['emergency'] = False
        self.q.put(('write', list(msg.data)))

    def _on_estop(self, msg):
        if msg.data:
            self.state['emergency'] = True  # 진행 중인 글쓰기 루프 중단용 플래그
            # 진행 중인 모션을 실제로 즉시 정지 (fire-and-forget, 응답 대기 안 함)
            req = MoveStop.Request()
            req.stop_mode = DR_QSTOP
            self.move_stop_cli.call_async(req)
            self.status_pub.publish(String(data="ERROR"))
            self.get_logger().error("비상정지 수신 — 로봇 정지 명령 전송")

    def _on_home(self, msg):
        if msg.data:
            self.q.put(('home', None))

    def _on_reset(self, msg):
        if msg.data:
            self.q.put(('reset', None))

    def _on_jog(self, msg):
        """
        연속 조그: 네이티브 jog 서비스 직접 호출 (큐 거치지 않음).
        데이터 포맷: [axis_idx(0~5), speed_signed]
          speed_signed != 0 → 해당 속도로 연속 이동 시작
          speed_signed == 0 → 정지
        """
        if len(msg.data) < 2:
            return
        axis_idx = int(msg.data[0])
        speed    = float(msg.data[1])
        req = Jog.Request()
        req.jog_axis       = JOG_AXIS_TASK_X + axis_idx
        req.move_reference = DR_BASE_REF
        req.speed          = speed
        self.jog_cli.call_async(req)  # fire-and-forget


class MotionWorker:
    """메인 스레드에서 큐를 소비하며 DSR 모션을 실행한다."""

    def __init__(self, sub_node: SubscriberNode, cmd_queue: queue.Queue, state: dict):
        self.sub   = sub_node
        self.q     = cmd_queue
        self.state = state
        self.log   = sub_node.get_logger()

        from DSR_ROBOT2 import (
            movel, movej, movesx, posx, posj, get_current_posx, set_robot_mode,
            task_compliance_ctrl, release_compliance_ctrl,
            set_desired_force, release_force, wait,
            set_tool, set_tcp,
            DR_FC_MOD_ABS,
        )
        from DRFC import ROBOT_MODE_AUTONOMOUS

        self.movel  = movel
        self.movej  = movej
        self.movesx = movesx
        self.posx   = posx
        self.posj   = posj
        self.get_current_posx = get_current_posx

        # 힘/순응 제어 함수
        self.task_compliance_ctrl    = task_compliance_ctrl
        self.release_compliance_ctrl = release_compliance_ctrl
        self.set_desired_force       = set_desired_force
        self.release_force           = release_force
        self.wait                    = wait
        self.DR_FC_MOD_ABS           = DR_FC_MOD_ABS

        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
        # 힘 제어가 올바른 붓 끝 기준으로 동작하도록 Tool/TCP 지정 (test1.py 와 동일)
        set_tool("Tool Weight")
        set_tcp("GripperDA_v1")
        self.log.info("DSR API 초기화 완료 (자율 모드, 힘 제어 지원)")

    def _enable_write_force(self):
        """순응 제어 + 목표 힘(-3N) ON — 붓을 종이에 일정 힘으로 누른다."""
        fd = [0, 0, WRITE_FORCE_Z, 0, 0, 0]
        self.task_compliance_ctrl(WRITE_STIFFNESS)
        self.wait(0.1)
        self.set_desired_force(fd, dir=WRITE_FORCE_DIR, mod=self.DR_FC_MOD_ABS)

    def _disable_write_force(self):
        """힘 제어 → 순응 제어 순서로 반드시 해제한다."""
        self.release_force()
        self.wait(0.1)
        self.release_compliance_ctrl()

    def _status(self, s):
        self.sub.status_pub.publish(String(data=s))

    def run(self):
        while rclpy.ok():
            try:
                cmd, data = self.q.get(timeout=0.1)
            except queue.Empty:
                continue

            self.state['busy'] = True
            try:
                if   cmd == 'write': self._do_write(data)
                elif cmd == 'home':  self._do_home()
                elif cmd == 'reset': self._do_reset()
            except Exception as e:
                self.log.error(f"{cmd} 실행 실패: {e}")
                self._status("ERROR")
            finally:
                self.state['busy'] = False

    # ── 개별 동작 ──────────────────────────────────────────────────────────

    def _do_write(self, data):
        """
        웨이포인트(7개 값 × N)를 힘 제어로 실행한다. (test1.py execute_path 이식)

        연속된 pen_down 점을 한 획으로 묶어서:
          1. 획 시작점 위 hover 로 빠르게 이동
          2. write_z(표면 +3mm)까지 천천히 하강 — 아직 종이 위
          3. 순응 제어 + 힘 제어(-3N) ON → 붓이 종이에 닿아 일정 힘 유지
          4. movesx 로 획 실행 (50점 단위 분할)
          5. 힘 제어 OFF → hover 로 복귀
        pen_up 점은 hover 높이에서 movel 로 빠르게 공이동한다.
        """
        self.log.info("글쓰기 시작")
        self._status("WRITING")

        # flat 데이터 → [(x, y, z, rx, ry, rz, pen), ...]
        pts = [data[i:i+7] for i in range(0, len(data) - 6, 7)]
        total = len(pts)
        if total == 0:
            self._status("IDLE")
            self.log.warning("웨이포인트가 비어 있음")
            return

        stroke_count  = 0
        force_enabled = False
        i = 0
        try:
            while i < total:
                if self.state.get('emergency'):
                    self.log.warning("비상정지로 글쓰기 중단")
                    self._status("ERROR")
                    return

                x, y, z, rx, ry, rz, pen = pts[i]

                if not int(pen):
                    # 공이동: 받은 hover 높이(z)에서 빠르게 이동
                    self.movel(self.posx(x, y, z, rx, ry, rz),
                               vel=TRAVEL_VEL, acc=TRAVEL_ACC)
                    i += 1
                    continue

                # 한 획(연속 pen_down) 포인트 수집.
                # pen_down z = 표면(surface_z) → 접근/이동 높이를 재계산한다.
                surface_z = z
                write_z   = surface_z + WRITE_Z_BIAS   # 힘 제어가 눌러줄 접근 높이
                hover_z   = surface_z + HOVER_HEIGHT
                stroke_pts = []
                first = last = None
                while i < total and int(pts[i][6]) == 1:
                    bx, by, _bz, brx, bry, brz, _ = pts[i]
                    stroke_pts.append(self.posx(bx, by, write_z, brx, bry, brz))
                    if first is None:
                        first = (bx, by, brx, bry, brz)
                    last = (bx, by, brx, bry, brz)
                    i += 1

                fx, fy, frx, fry, frz = first
                lx, ly, lrx, lry, lrz = last

                # 1. 획 시작점 위 hover 로 이동
                self.movel(self.posx(fx, fy, hover_z, frx, fry, frz),
                           vel=TRAVEL_VEL, acc=TRAVEL_ACC)
                # 2. write_z 까지 천천히 하강 (표면 3mm 위, 아직 미접촉)
                self.movel(self.posx(fx, fy, write_z, frx, fry, frz),
                           vel=PROBE_VEL, acc=PROBE_ACC)

                try:
                    # 3. 순응 제어 + 힘 제어 ON (-3N 유지)
                    self._enable_write_force()
                    force_enabled = True

                    # 4. 획 실행 (50점 단위 분할)
                    for s in range(0, len(stroke_pts), MOVESX_MAX_PTS):
                        chunk = stroke_pts[s:s + MOVESX_MAX_PTS]
                        if len(chunk) == 1:
                            self.movel(chunk[0], vel=WRITE_VEL, acc=WRITE_ACC)
                        else:
                            self.movesx(chunk, vel=WRITE_VEL, acc=WRITE_ACC)
                finally:
                    # 5. 힘 제어 OFF → hover 복귀 (반드시 해제)
                    if force_enabled:
                        self._disable_write_force()
                        force_enabled = False
                    self.movel(self.posx(lx, ly, hover_z, lrx, lry, lrz),
                               vel=TRAVEL_VEL, acc=TRAVEL_ACC)

                stroke_count += 1
                pct = 100 * i // total
                self.log.info(f"  획 {stroke_count} 완료  ({pct}%  {i}/{total})")
        finally:
            if force_enabled:
                self._disable_write_force()

        self._status("IDLE")
        self.log.info("글쓰기 완료")

    def _do_home(self):
        self.log.info("원점 복귀")
        self._status("HOMING")
        self.movej(self.posj(*HOME_JOINT), vel=40, acc=40)
        self._status("IDLE")
        self.log.info("원점 복귀 완료")

    def _do_reset(self):
        self.log.info("에러 리셋")
        from DSR_ROBOT2 import set_robot_mode
        from DRFC import ROBOT_MODE_AUTONOMOUS
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
        self.state['emergency'] = False
        self._status("IDLE")


def main(args=None):
    rclpy.init(args=args)

    cmd_queue = queue.Queue()
    state = {'emergency': False, 'busy': False}

    # 1) DSR 전용 노드 — DSR 함수가 내부적으로만 spin. 우리가 spin하지 않는다.
    dsr_node = rclpy.create_node('dsr_motion', namespace=ROBOT_ID)
    DR_init.__dsr__id    = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL
    DR_init.__dsr__node  = dsr_node

    # 2) 구독 노드 — 전용 executor로 백그라운드 스레드에서 spin
    #    (rclpy.spin/spin_until_future_complete는 전역 executor를 공유하므로,
    #     DSR 함수의 내부 spin과 충돌하지 않도록 별도 executor 사용)
    sub_node = SubscriberNode(cmd_queue, state)
    sub_exec = SingleThreadedExecutor()
    sub_exec.add_node(sub_node)

    spin_thread = threading.Thread(target=sub_exec.spin, daemon=True)
    spin_thread.start()

    # 3) 메인 스레드에서 모션 워커 실행 (DSR 함수 여기서만 호출)
    worker = MotionWorker(sub_node, cmd_queue, state)
    try:
        worker.run()
    except KeyboardInterrupt:
        pass
    finally:
        sub_node.destroy_node()
        dsr_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

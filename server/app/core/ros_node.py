import threading
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float32MultiArray, String

from .robot_state import job_state, schedule_broadcast, robot_live, schedule_robot_broadcast

# 로봇 상태 문자열(pub_sub.py 발행) → job_state.status 매핑
STATUS_MAP = {
    "WRITING": "writing",
    "HOMING":  "idle",
    "IDLE":    "done",
    "ERROR":   "error",
}

# 도화지 좌표 → 로봇 베이스 좌표 변환 (A4 4모서리 재실측, 2026-07-09 / KIM 방향 기준)
#
# 실측 모서리(BASE, mm) — 이미지 기준:
#   좌상단 = (293.01, 193.98)
#   우상단 = (290.65, -14.30)
#   좌하단 = ( -1.47, 192.33)
#   우하단 = ( -1.58, -14.61)  ← 원점 = 페이지 원점(글자 좌측 하단)
# 글씨 방향(KIM): 읽는 방향 K→I→M = 이미지 아래→위 = 로봇 +X,
#                 글자 위(baseline→top) = 이미지 왼쪽 = 로봇 +Y
#   페이지 원점(글자 좌측 하단) = 우하단 모서리
#   페이지 +X(읽는 방향) = 원점 → 우상단  (≈ 로봇 +X)
#   페이지 +Y(글자 위)   = 원점 → 좌하단  (≈ 로봇 +Y)
# 단위 방향벡터는 실측값으로 산출해 용지의 미세 기울기까지 반영한다.
PAPER_ORIGIN_XY = (-1.58, -14.61)          # 우하단: 페이지 원점 (글자 좌측 하단)
PAGE_X_DIR      = (0.999999, 0.001061)     # 원점→우상단 정규화 (읽는 방향, +px)
PAGE_Y_DIR      = (0.000532, 1.000000)     # 원점→좌하단 정규화 (글자 위,   +py)

PAPER_ORIGIN_Z  = 98.0        # TODO: 종이 접촉 z 실측값으로 교체 (현재 pub_sub 힘제어가 자동 감지)
HOVER_HEIGHT    = 30.0
WRITE_RX, WRITE_RY, WRITE_RZ = 90.0, 180.0, 90.0


def paper_to_robot(px, py, pen_down):
    """
    도화지 좌표 (path_generator 출력, mm) → 로봇 베이스 좌표 변환.
    AL 모서리를 원점으로, AL→L(읽는 방향)·AL→A(글자 위) 방향으로 px·py 를 실제 mm 만큼 이동.
    글자 크기(mm)를 1:1 로 보존한다.
    """
    ox, oy = PAPER_ORIGIN_XY
    rx = ox + px * PAGE_X_DIR[0] + py * PAGE_Y_DIR[0]
    ry = oy + px * PAGE_X_DIR[1] + py * PAGE_Y_DIR[1]
    rz = PAPER_ORIGIN_Z if pen_down else PAPER_ORIGIN_Z + HOVER_HEIGHT
    return rx, ry, rz


class WritingPublisherNode(Node):
    def __init__(self):
        super().__init__('writing_publisher')
        self.moving_pub    = self.create_publisher(Float32MultiArray, '/robot/target_moving', 10)
        self.estop_pub     = self.create_publisher(Bool,              '/safety/emergency_stop', 10)
        self.home_pub      = self.create_publisher(Bool,              '/robot/go_home', 10)
        self.reset_pub     = self.create_publisher(Bool,              '/robot/error_reset', 10)
        self.jog_pub       = self.create_publisher(Float32MultiArray, '/robot/jog', 10)
        self.grip_pub      = self.create_publisher(Bool,              '/robot/grip', 10)

        # 로봇 상태 구독 → job_state 갱신 + WebSocket 브로드캐스트
        self.status_sub = self.create_subscription(
            String, '/robot/status', self._on_status, 10)
        # 로봇 현재 좌표(User_102) 구독 → robot_live 갱신 + /ws/robot 브로드캐스트
        self.pose_sub = self.create_subscription(
            Float32MultiArray, '/robot/current_pose', self._on_pose, 10)
        # TCP 외력(User_102) 구독 → robot_live 갱신 + /ws/robot 브로드캐스트
        self.force_sub = self.create_subscription(
            Float32MultiArray, '/robot/force', self._on_force, 10)
        # 종이 감지 센서 구독 → robot_live 갱신 + /ws/robot 브로드캐스트
        self.paper_sub = self.create_subscription(
            Bool, 'paper_sensor', self._on_paper, 10)
        # 획 진행 구독 [완료 획, 전체 획] → job_state 진행률/획 진행 갱신 + 브로드캐스트
        self.progress_sub = self.create_subscription(
            Float32MultiArray, '/robot/progress', self._on_progress, 10)

    def _on_status(self, msg):
        status = STATUS_MAP.get(msg.data, "idle")
        job_state.status = status
        if status == "done":
            job_state.progress_pct = 100
        elif status == "error":
            job_state.error_msg = "비상정지 또는 오류로 중단됨"
        self.get_logger().info(f"로봇 상태 수신: {msg.data} → {status}")
        schedule_broadcast()

    def _on_progress(self, msg):
        if len(msg.data) < 2:
            return
        done, total = int(msg.data[0]), int(msg.data[1])
        job_state.current_stroke = done
        job_state.total_strokes = total
        # 완료 상태(pct=100)는 /robot/status(IDLE→done)에서 확정하므로 여기선 99%까지만.
        if total > 0 and done < total:
            job_state.progress_pct = int(done / total * 100)
        # 획 인덱스로 현재 글자 역추적 (done=0 이면 첫 글자를 미리 표시)
        chars = job_state.stroke_chars
        if chars:
            idx = min(max(done, 1), len(chars)) - 1
            job_state.current_char = chars[idx]
        schedule_broadcast()

    def _on_pose(self, msg):
        if len(msg.data) >= 6:
            robot_live.tcp_position = [round(float(v), 2) for v in msg.data[:6]]
            schedule_robot_broadcast()

    def _on_force(self, msg):
        if len(msg.data) >= 6:
            robot_live.tcp_force = [round(float(v), 2) for v in msg.data[:6]]
            schedule_robot_broadcast()

    def _on_paper(self, msg):
        if robot_live.paper_present != msg.data:
            robot_live.paper_present = bool(msg.data)
            self.get_logger().info(f"종이 감지: {'있음' if msg.data else '없음'}")
        else:
            robot_live.paper_present = bool(msg.data)
        schedule_robot_broadcast()

    def publish_waypoints(self, path):
        data = []
        for px, py, pen_down in path:
            rx, ry, rz = paper_to_robot(px, py, pen_down)
            data.extend([rx, ry, rz, WRITE_RX, WRITE_RY, WRITE_RZ, float(pen_down)])
        msg = Float32MultiArray()
        msg.data = data
        self.moving_pub.publish(msg)
        self.get_logger().info(f"웨이포인트 {len(path)}개 발행 완료")

    def publish_emergency_stop(self, stop: bool = True):
        msg = Bool(); msg.data = stop
        self.estop_pub.publish(msg)

    def publish_go_home(self):
        msg = Bool(); msg.data = True
        self.home_pub.publish(msg)

    def publish_error_reset(self):
        msg = Bool(); msg.data = True
        self.reset_pub.publish(msg)

    def publish_grip(self, grip: bool):
        """True=그립(집기), False=언그립(놓기)"""
        msg = Bool(); msg.data = grip
        self.grip_pub.publish(msg)

    def publish_jog(self, axis: str, direction: int, moving: bool, speed: float = 30.0):
        """
        연속 조그 명령 발행.
        데이터 포맷: [axis_idx(0~5), speed_signed]
          moving=True  → speed*direction 속도로 연속 이동
          moving=False → 0 (정지)
        """
        axis_map = {'x': 0, 'y': 1, 'z': 2, 'rx': 3, 'ry': 4, 'rz': 5}
        axis_idx = axis_map.get(axis, 2)
        speed_signed = (speed * direction) if moving else 0.0
        msg = Float32MultiArray()
        msg.data = [float(axis_idx), float(speed_signed)]
        self.jog_pub.publish(msg)


# 싱글톤 노드 — FastAPI 시작 시 한 번만 초기화
_node: WritingPublisherNode = None
_thread: threading.Thread = None


def get_ros_node() -> WritingPublisherNode:
    return _node


def start_ros_node():
    global _node, _thread

    def _spin():
        global _node
        rclpy.init()
        _node = WritingPublisherNode()
        rclpy.spin(_node)
        _node.destroy_node()
        rclpy.shutdown()

    _thread = threading.Thread(target=_spin, daemon=True)
    _thread.start()

import threading
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float32MultiArray, String

from .robot_state import job_state, schedule_broadcast

# 로봇 상태 문자열(pub_sub.py 발행) → job_state.status 매핑
STATUS_MAP = {
    "WRITING": "writing",
    "HOMING":  "idle",
    "IDLE":    "done",
    "ERROR":   "error",
}

# 도화지 좌표 → 로봇 베이스 좌표 변환 상수 (writing_node.py 와 동일)
PAPER_ORIGIN_X  = 567.77
PAPER_ORIGIN_Y  = -155.60
PAPER_ORIGIN_Z  = 98.0
HOVER_HEIGHT    = 30.0
WRITE_RX, WRITE_RY, WRITE_RZ = 90.0, 180.0, 90.0


def paper_to_robot(px, py, pen_down):
    """
    도화지 좌표 (path_generator 출력) → 로봇 베이스 좌표 변환
    도화지 오른쪽 = 로봇 Y 증가, 도화지 위쪽 = 로봇 X 감소
    """
    rx = PAPER_ORIGIN_X - py
    ry = PAPER_ORIGIN_Y + px
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

        # 로봇 상태 구독 → job_state 갱신 + WebSocket 브로드캐스트
        self.status_sub = self.create_subscription(
            String, '/robot/status', self._on_status, 10)

    def _on_status(self, msg):
        status = STATUS_MAP.get(msg.data, "idle")
        job_state.status = status
        if status == "done":
            job_state.progress_pct = 100
        elif status == "error":
            job_state.error_msg = "비상정지 또는 오류로 중단됨"
        self.get_logger().info(f"로봇 상태 수신: {msg.data} → {status}")
        schedule_broadcast()

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

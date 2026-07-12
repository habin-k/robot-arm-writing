import re

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool

try:
    import serial
except ImportError:
    serial = None


class ArduinoSensorPublisher(Node):
    """Arduino 시리얼 센서값을 읽어 종이 감지 여부를 Bool 토픽으로 발행한다."""

    def __init__(self):
        super().__init__('paper_sensor_publisher')

        self.declare_parameter('port', '/dev/ttyACM0')
        self.declare_parameter('baudrate', 9600)
        self.declare_parameter('topic', 'paper_sensor')
        self.declare_parameter('timer_period', 0.05)

        self.port = self.get_parameter('port').value
        self.baudrate = self.get_parameter('baudrate').value
        topic = self.get_parameter('topic').value
        timer_period = self.get_parameter('timer_period').value

        self.publisher = self.create_publisher(Bool, topic, 10)
        self.serial_port = self.open_serial()
        self.timer = self.create_timer(timer_period, self.read_and_publish)

    def open_serial(self):
        if serial is None:
            raise RuntimeError(
                'pyserial is not installed. Install it with: sudo apt install python3-serial'
            )

        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
        except serial.SerialException as exc:
            raise RuntimeError(f'Failed to open serial port {self.port}: {exc}') from exc

        self.get_logger().info(
            f'Reading Arduino sensor data from {self.port} at {self.baudrate} baud'
        )
        return ser

    def read_and_publish(self):
        """시리얼 한 줄을 읽고 0/1 센서값이면 ROS Bool 메시지로 변환한다."""
        try:
            line = self.serial_port.readline().decode(errors='ignore').strip()
        except serial.SerialException as exc:
            self.get_logger().error(f'Serial read failed: {exc}')
            return

        if not line:
            return

        sensor_value = self.parse_sensor_value(line)
        if sensor_value is None:
            self.get_logger().debug(f'Ignoring serial line: {line}')
            return

        msg = Bool()
        msg.data = sensor_value == 0
        self.publisher.publish(msg)

        if msg.data:
            self.get_logger().info('Object detected')
        else:
            self.get_logger().info('No object')

    @staticmethod
    def parse_sensor_value(line):
        """'0', '1', 'Sensor = 0/1' 형식의 센서 문자열을 정수값으로 파싱한다."""
        if line in ('0', '1'):
            return int(line)

        match = re.search(r'Sensor\s*=\s*([01])', line)
        if match:
            return int(match.group(1))

        return None

    def destroy_node(self):
        if hasattr(self, 'serial_port') and self.serial_port.is_open:
            self.serial_port.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None

    try:
        node = ArduinoSensorPublisher()
        rclpy.spin(node)
    except RuntimeError as exc:
        if node is not None:
            node.get_logger().error(str(exc))
        else:
            print(exc)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

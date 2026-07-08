import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from onrobot_rg_msgs.msg import OnRobotRGInput


class FakeTaskInputs(Node):
    def __init__(self):
        super().__init__("fake_task_inputs")

        self.declare_parameter("paper_available", True)
        self.declare_parameter("gripper_width_mm", 20.0)
        self.declare_parameter("publish_hz", 2.0)

        self.paper_pub = self.create_publisher(Bool, "/paper_sensor", 10)
        self.gripper_pub = self.create_publisher(OnRobotRGInput, "/OnRobotRGInput", 10)

        publish_hz = self.get_parameter("publish_hz").value
        timer_period = 1.0 / publish_hz if publish_hz > 0.0 else 0.5
        self.timer = self.create_timer(timer_period, self.publish_inputs)

        self.get_logger().info(
            "fake inputs started: /paper_sensor, /OnRobotRGInput"
        )

    def publish_inputs(self):
        paper_available = bool(self.get_parameter("paper_available").value)
        width_mm = float(self.get_parameter("gripper_width_mm").value)
        width_01mm = max(0, int(width_mm * 10.0))

        paper_msg = Bool()
        paper_msg.data = paper_available
        self.paper_pub.publish(paper_msg)

        gripper_msg = OnRobotRGInput()
        gripper_msg.gfof = 0
        gripper_msg.ggwd = width_01mm
        gripper_msg.gwdf = width_01mm
        gripper_msg.gsta = 0b00000010
        self.gripper_pub.publish(gripper_msg)


def main(args=None):
    rclpy.init(args=args)
    node = FakeTaskInputs()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

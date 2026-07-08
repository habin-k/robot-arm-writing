import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from onrobot_rg_msgs.msg import OnRobotRGInput
import time
import DR_init

# 1. 초기화 변수 선언
DR_init.__dsr__id = "dsr01"
DR_init.__dsr__model = "m0609"

VEL, ACC = 30, 30

# 2. ROS 2 통신을 담당할 클래스 정의
class TaskStateNode(Node):
    def __init__(self):
        super().__init__('task_manager', namespace='dsr01')
        
        # 상태를 공유할 플래그 변수
        self.start_task = False
        self.gripper_width = 0.0
        
        # 서브스크라이버 (예: 외부에서 작업 시작 신호 받기)
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
        

    def paper_callback(self, msg):
        # self.get_logger().info(f"종이 센서 값 수신: {msg.data}")
        self.start_task = msg.data

    def gripper_width_callback(self, msg):
        # self.get_logger().info(f"그리퍼 너비 수신: {msg.gwdf / 10.0}")
        self.gripper_width = msg.gwdf / 10.0 
        
         
class TaskManager:
    def __init__(self, node):
        self.node = node
        
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

        
    #—————————단위 동작 함수들———————————
    def grip(self):
        self.node.get_logger().info("그리퍼 닫기")
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(1, 1)
        self.wait(1)
        
    def ungrip(self):
        self.node.get_logger().info("그리퍼 열기")
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(2, 1)
        self.wait(1) 
     
    def grip_pen(self):
        self.node.get_logger().info("펜 파지")
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
        self.movel(self.posx(303, 9, 197, 90, 180, 0), vel=VEL, acc=ACC)   
        self.movel(self.posx(0, 0, -60, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)   
        self.grip()
        return True
    
    def return_pen(self):
        self.node.get_logger().info("펜 복귀")
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
        self.movel(self.posx(303, 9, 197, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(0, 0, -60, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.wait(0.5)
        self.ungrip()
        return True

    def grip_stamp(self):
        self.node.get_logger().info("도장 파지")
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
        self.movel(self.posx(305, 103, 197, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(305, 103, 33, 90, 180, 0), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.grip()
        return True
    
    def stamp(self):
        fd = [0, 0, -20, 0, 0, 0]
        fctrl_dir = [0, 0, 1, 0, 0, 0]

        self.node.get_logger().info("도장 찍기")
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
        self.movel(self.posx(305, 103, 130, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(527, 99, 130, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(527, 99, 120, 90, 180, 0), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.task_compliance_ctrl([2000, 2000, 500, 200, 200, 200])
        self.wait(1)
        self.set_desired_force(fd, fctrl_dir, mod=self.DR_FC_MOD_REL)
        self.wait(1)
        self.release_force()
        self.wait(0.5)
        self.release_compliance_ctrl()
        self.wait(0.5)
        self.movel(self.posx(527, 99, 100, 90, 180, 0), vel=VEL, acc=ACC)
        return True

    def return_stamp(self):
        fd = [0, 0, -20, 0, 0, 0]
        fctrl_dir = [0, 0, 1, 0, 0, 0]

        self.node.get_logger().info("도장 복귀")
        self.movel(self.posx(527, 99, 130, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(305, 103, 130, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(305, 103, 33, 90, 180, 0), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.task_compliance_ctrl([2000, 2000, 500, 200, 200, 200])
        self.wait(1)
        self.set_desired_force(fd, fctrl_dir, mod=self.DR_FC_MOD_REL)
        self.wait(1)
        self.release_force()
        self.wait(0.5)
        self.release_compliance_ctrl()
        self.wait(0.5)
        self.ungrip()
        return True
    
    def is_gripped(self):
        width = self.node.gripper_width
        
        if width is None:
            self.node.get_logger().warn("그리퍼 데이터 수신 실패")
            return False

        if width < 10:
            self.node.get_logger().error(f"파지 실패: width={width:.2f}")
            return False
        
        self.node.get_logger().info(f"파지 확인: width={width:.2f}")
        return True

    def eject_paper(self):
        fd = [0, 0, -0.1, 0, 0, 0]
        fctrl_dir = [0, 0, 1, 0, 0, 0]

        self.node.get_logger().info("종이 배출 테스트 시작")
        self.movel(self.posx(462, -4, 197, 90, 180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -4, 75, 90, 180, 90), vel=VEL, acc=ACC)
        self.wait(0.5)
        self.task_compliance_ctrl([2000, 2000, 500, 200, 200, 200])
        self.wait(1)
        self.set_desired_force(fd, fctrl_dir, mod=self.DR_FC_MOD_REL)
        self.wait(3)
        self.movel(self.posx(0, -80, 0, 0, 0, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL, ref=self.DR_BASE)
        self.wait(0.5)
        self.release_force()
        self.wait(0.5)
        self.release_compliance_ctrl()
        self.wait(0.5)
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
        self.node.get_logger().info("종이 배출 완료")
        return True
    
    def return_home(self):
        self.node.get_logger().info("원점 복귀")
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
    

    def run_once(self):
        self.grip_pen()
        self.return_pen()
        self.grip_stamp()
        self.stamp()
        self.return_stamp()
        self.eject_paper()
        self.return_home()



def main(args=None):
    DR_init.__dsr__id = "dsr01"
    DR_init.__dsr__model = "m0609"
    
    rclpy.init(args=args)
    node = TaskStateNode()
    
    DR_init.__dsr__node = node
    
    sequencer = TaskManager(node)
    node.get_logger().info("task_manager_new 시작")
    
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)

            if node.start_task:
                node.start_task = False
                sequencer.run_once()
            else:
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
         
if __name__ == "__main__":
    main()

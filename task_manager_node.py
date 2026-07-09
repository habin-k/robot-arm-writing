import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from onrobot_rg_msgs.msg import OnRobotRGInput
import time
import DR_init
from enum import Enum
# 1. 초기화 변수 선언
DR_init.__dsr__id = "dsr01"
DR_init.__dsr__model = "m0609"

VEL, ACC = 50, 50

class RobotState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    MANUAL_REQUIRED = "manual_required"

# 2. ROS 2 통신을 담당할 클래스 정의
class TaskStateNode(Node):
    def __init__(self):
        super().__init__('task_manager', namespace='dsr01')
        
        # 상태를 공유할 플래그 변수
        self.start_task = False
        self.gripper_width = 0.0
        # 최신 그리퍼 값 확인용 None 초기화 / 시퀀스 추가
        self.gripper_width = None
        self.gripper_width_seq = 0

        self.robot_state = RobotState.IDLE
        
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
        # 그리퍼 메시지 갱신 여부 추가
        self.gripper_width_seq += 1
        
         
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

    # run_once 중에도 /OnRobotRGInput 콜백을 처리하기 위한 콜백함수
    def drain_gripper_callbacks(self, duration_sec=0.2):
        deadline = time.monotonic() + duration_sec
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.02)

    # 그리퍼 명령 이후 최신 width 메시지를 기다리려고 추가했던 함수
    def wait_for_gripper_update(self, previous_seq, timeout_sec=2.0, settle_sec=0.2):
        deadline = time.monotonic() + timeout_sec
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.1)
            if self.node.gripper_width_seq > previous_seq:
                self.drain_gripper_callbacks(settle_sec)
                return True
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
        pass
    
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
    
    def go_home(self):
        self.node.get_logger().info("원점으로 이동중")
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=30, acc=30)
    
    def reset(self):
        pass

    def run_once(self):
        try:
            self.go_home()
            self.ungrip()
            self.grip_pen()
            self.is_gripped("펜")  

            self.write()

            self.return_pen()

            self.grip_stamp()
            self.is_gripped("도장")          
            self.stamp()
            self.return_stamp()

            self.eject_paper()
            self.go_home()
            self.node.robot_state = RobotState.IDLE

        except Exception as e:
            self.node.get_logger().error(f"작업 중단: {e}")
            self.node.get_logger().error("관리자 수동 복구 모드로 진입합니다. Reset 필요.")
            self.node.robot_state = RobotState.MANUAL_REQUIRED # 관리자 수동 모드 진입 # RobotState 클래스 정의 시 구현

        
        finally:
            pass



def main(args=None):
    DR_init.__dsr__id = "dsr01"
    DR_init.__dsr__model = "m0609"
    
    rclpy.init(args=args)
    node = TaskStateNode()
    
    DR_init.__dsr__node = node
    
    sequencer = TaskManager(node)

    sequencer.set_tool("GripperDA_v1")
    sequencer.set_tcp("Tool Weight")
    
    node.get_logger().info("task_manager_new 시작")
    
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)

            if node.start_task and node.robot_state == RobotState.IDLE:
                node.start_task = False
                node.robot_state = RobotState.RUNNING
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

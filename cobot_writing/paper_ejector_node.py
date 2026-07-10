"""
paper_ejector_node.py — 종이 집어서 배출하는 모션 엔진.

기존 단독 노드(main 안에 모션이 다 있던 것)를 재사용 가능한 PaperEjector 클래스로
분리한 것. writer.py 의 PenWriter 와 동일한 패턴이다.

두 가지로 쓸 수 있다:

  1) import 해서 task_manager_node.py 등에서 (init_robot=False, tool/tcp는 호출자가 관리):
        from cobot_writing.paper_ejector_node import PaperEjector
        ejector = PaperEjector(node, init_robot=False)
        ejector.eject()          # 종이 배출 모션 (블로킹, 끝나면 리턴)

  2) 단독 실행 테스트 (기존 `ros2 run cobot_writing paper_ejector` 와 동일):
        ros2 run cobot_writing paper_ejector

전제: PaperEjector() 생성 전에 DR_init.__dsr__node 가 설정돼 있어야 한다
      (DSR_ROBOT2 import 시점에 읽힘).
"""

import rclpy
import DR_init


ROBOT_ID = 'dsr01'
ROBOT_MODEL = 'm0609'
VEL = 25
ACC = 25


class PaperEjector:
    """종이 집어서 배출함으로 옮기는 모션 엔진. (기존 paper_ejector main 로직을 클래스화)"""

    def __init__(self, node, *, init_robot=True):
        """
        node       : logger 를 쓸 rclpy 노드 (task_manager 노드나 단독 노드)
        init_robot : True 면 tool/tcp 를 여기서 설정한다 (단독 실행용).
                     task_manager 처럼 호출자가 tool/tcp 를 이미 관리하면 False 로 넘긴다.
        """
        self.node = node
        self.log = node.get_logger()

        from DSR_ROBOT2 import (
            movej,
            movel,
            wait,
            set_digital_output,
            set_tool,
            set_tcp,
            DR_MV_MOD_REL,
        )
        from DR_common2 import posj, posx

        self.movej = movej
        self.movel = movel
        self.wait = wait
        self.set_digital_output = set_digital_output
        self.posj = posj
        self.posx = posx
        self.DR_MV_MOD_REL = DR_MV_MOD_REL

        if init_robot:
            # 단독 실행: tool/tcp 를 여기서 설정. task_manager 통합(False) 시엔 호출자가 관리.
            set_tool('Tool Weight')
            set_tcp('GripperDA_v1')

    def grip(self):
        self.log.info('grip')
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(1, 1)
        self.wait(1)

    def ungrip(self):
        self.log.info('ungrip')
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(2, 1)
        self.wait(1)

    def eject(self):
        """종이 배출 기본 모션 (블로킹). 좌표는 기존 단독 노드와 100% 동일."""
        self.log.info('paper eject basic motion start')
        self.movej(self.posj(0, 0, 90, 0, 90, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(462, 60, 85, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -180, 85, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -160, 85, 90, 100, 0), vel=VEL, acc=ACC)
        self.grip()
        self.movel(self.posx(462, -160, 85, 90, 180, 0), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -160, 360, 160, 180, 70), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -50, 360, 170, -180, 77.62), vel=VEL, acc=ACC)
        self.movel(self.posx(462, -50, 360, 270, -180, 90), vel=VEL, acc=ACC)
        self.movel(self.posx(664, -50, 138, 270, -180, 90), vel=VEL, acc=ACC)
        self.movej(self.posj(0, 0, 0, 0, -30, 0), vel=VEL, acc=ACC, mod=self.DR_MV_MOD_REL)
        self.ungrip()
        self.log.info('paper eject basic motion done')
        return True


def main(args=None):
    rclpy.init(args=args)

    DR_init.__dsr__id = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL

    node = rclpy.create_node('paper_ejector', namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    try:
        ejector = PaperEjector(node, init_robot=True)
        ejector.eject()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

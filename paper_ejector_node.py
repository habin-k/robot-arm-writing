import rclpy


ROBOT_ID = 'dsr01'
ROBOT_MODEL = 'm0609'
VEL = 25
ACC = 25


def main(args=None):
    rclpy.init(args=args)

    import DR_init

    DR_init.__dsr__id = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL

    node = rclpy.create_node('paper_ejector', namespace=ROBOT_ID)
    DR_init.__dsr__node = node
    log = node.get_logger()

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

    def grip():
        log.info('grip')
        set_digital_output(1, 0)
        set_digital_output(2, 0)
        set_digital_output(1, 1)
        wait(1)

    def ungrip():
        log.info('ungrip')
        set_digital_output(1, 0)
        set_digital_output(2, 0)
        set_digital_output(2, 1)
        wait(1)

    try:
        set_tool('GripperDA_v1')
        set_tcp('Tool Weight')

        log.info('paper eject basic motion start')
        movej(posj(0,0,90,0,90,0), vel=VEL, acc=ACC)
        movel(posx(462, 60, 85, 90, 180, 0), vel=VEL, acc=ACC)
        movel(posx(462, -180, 85, 90, 180, 0), vel=VEL, acc=ACC)
        movel(posx(462, -160, 85, 90, 100, 0), vel=VEL, acc=ACC)
        grip()
        movel(posx(462, -160, 85, 90, 180, 0), vel=VEL, acc=ACC)
        movel(posx(462, -160, 360, 160, 180, 70), vel=VEL, acc=ACC)
        movel(posx(462, -50, 360, 170, -180, 77.62), vel=VEL, acc=ACC)
        movel(posx(462, -50, 360, 270, -180, 90), vel=VEL, acc=ACC)
        movel(posx(664, -50, 138, 270, -180, 90), vel=VEL, acc=ACC)        
        movej(posj(0, 0, 0, 0, -30, 0), vel=VEL, acc=ACC, mod=DR_MV_MOD_REL)
        ungrip()
        log.info('paper eject basic motion done')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

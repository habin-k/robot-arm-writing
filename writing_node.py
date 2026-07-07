#!/usr/bin/env python3
"""
Doosan M0609 글씨 쓰기 ROS2 노드

실행:
    ros2 run cobot_writing writing_node --ros-args -p text:="Hello World"

파라미터:
    text                  (str)   쓸 문구. \\n 으로 줄바꿈
    font_name             (str)   폰트 선택 (기본: regular)
                                  선택: regular, bold, light, condensed, extended, brother
    char_height_mm        (float) 대문자 높이 mm (기본: 25.0)
    paper_width_mm        (float) 도화지 가로 mm (기본: 210.0 = A4)
    paper_height_mm       (float) 도화지 세로 mm (기본: 297.0 = A4)
    margin_mm             (float) 여백 mm (기본: 25.0)
    skip_surface_detect   (bool)  종이 감지 건너뛰기 (기본: False)
"""

import time
import rclpy

# ── 로봇 설정 ──────────────────────────────────────────────────────────────
ROBOT_ID    = "dsr01"
ROBOT_MODEL = "m0609"
# ──────────────────────────────────────────────────────────────────────────

import DR_init
DR_init.__dsr__id    = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

from .path_generator import PathGenerator, PEN_DOWN


class WritingNode:
    """
    DSR API를 사용해 PathGenerator의 경로를 실제 로봇 동작으로 실행합니다.

    ┌─────────────────────────────────────────────────┐
    │  도화지 기준 좌표 → 로봇 베이스 좌표 매핑        │
    │  robot_X = PAPER_ORIGIN_X + path_x              │
    │  robot_Y = PAPER_ORIGIN_Y + path_y              │
    │  robot_Z = surface_z (쓰기) / + hover (이동)    │
    └─────────────────────────────────────────────────┘
    """

    # ── 사용자 설정값 (실제 셋업에 맞게 수정) ──────────────────────────────
    # A4 용지 좌측 하단 모서리의 로봇 베이스 좌표계 위치 (mm)
    # 주의: 도화지 오른쪽 = 로봇 Y 증가, 도화지 위쪽 = 로봇 X 감소
    PAPER_ORIGIN_X  = 567.77  # 측정값 (좌측 하단)
    PAPER_ORIGIN_Y  = -155.60 # 측정값 (좌측 하단)
    PAPER_ORIGIN_Z  = 98.0    # 측정값 (detect_surface 로 보정됨)

    # A4 용지 실측 크기 (mm)
    PAPER_WIDTH_MM  = 295.57  # 우측하단Y - 좌측하단Y = 139.97 - (-155.60)
    PAPER_HEIGHT_MM = 209.72  # 좌측하단X - 좌측상단X = 567.77 - 358.05

    # TCP 자세: GripperDA_v1 기준 펜이 수직 아래를 향하는 자세
    WRITE_RX, WRITE_RY, WRITE_RZ = 90.0, 180.0, 90.0

    # 획 간 이동 시 도화지 위 여유 높이 (mm)
    HOVER_HEIGHT    = 30.0

    # 글씨 쓰기 속도 [선속도, 각속도] (mm/s, deg/s)
    WRITE_VEL       = [20.0, 20.0]
    WRITE_ACC       = [40.0, 40.0]

    # 공이동 속도
    TRAVEL_VEL      = [80.0, 60.0]
    TRAVEL_ACC      = [100.0, 80.0]

    # 종이 감지: 하강 속도
    PROBE_VEL       = [8.0, 8.0]
    PROBE_ACC       = [15.0, 15.0]
    # 종이 감지: 도화지 표면 예상 높이보다 얼마나 위에서 하강 시작할지 (mm)
    PROBE_START_OFFSET = 80.0
    # 종이 감지: 접촉 판단 힘 임계값 (N)
    CONTACT_FORCE_Z = 20.0

    # 홈 자세 (조인트 각도, deg)
    HOME_JOINT      = [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]
    # ───────────────────────────────────────────────────────────────────────

    def __init__(self, logger):
        self._log = logger
        # DSR API 함수들 — main()에서 import 후 주입
        self._R = None

    def init_api(self):
        """DSR_ROBOT2 모듈을 import하고 로봇을 자율 모드로 설정합니다."""
        from DSR_ROBOT2 import (
            movej, movel, amovel, movesx,
            task_compliance_ctrl, release_compliance_ctrl,
            check_force_condition,
            get_tool_force, get_current_posx,
            set_velx, set_accx, set_robot_mode,
            set_tool, set_tcp,
            set_digital_output, wait,
            posj, posx,
            DR_BASE, DR_TOOL,
            DR_AXIS_Z,
            DR_MV_MOD_ABS,
        )
        from DRFC import ROBOT_MODE_AUTONOMOUS

        self._R = dict(
            movej=movej, movel=movel, amovel=amovel,
            movesx=movesx,
            task_compliance_ctrl=task_compliance_ctrl,
            release_compliance_ctrl=release_compliance_ctrl,
            check_force_condition=check_force_condition,
            get_tool_force=get_tool_force,
            get_current_posx=get_current_posx,
            set_velx=set_velx, set_accx=set_accx,
            set_robot_mode=set_robot_mode,
            set_digital_output=set_digital_output,
            wait=wait,
            posj=posj, posx=posx,
            DR_BASE=DR_BASE, DR_TOOL=DR_TOOL,
            DR_AXIS_Z=DR_AXIS_Z,
            DR_MV_MOD_ABS=DR_MV_MOD_ABS,
            ROBOT_MODE_AUTONOMOUS=ROBOT_MODE_AUTONOMOUS,
        )

        self._R['set_robot_mode'](ROBOT_MODE_AUTONOMOUS)
        set_tool("Tool Weight")
        set_tcp("GripperDA_v1")
        self._log.info("DSR API 초기화 완료")

    # ── 내부 유틸 ──────────────────────────────────────────────────────────

    def _posx(self, x, y, z):
        """쓰기 자세 고정 TCP 위치 생성"""
        return self._R['posx'](x, y, z,
                               self.WRITE_RX, self.WRITE_RY, self.WRITE_RZ)

    def _paper_to_robot(self, px, py, pz):
        """도화지 좌표 → 로봇 베이스 좌표 변환
        도화지 오른쪽 = 로봇 Y 증가, 도화지 위쪽 = 로봇 X 감소"""
        return (self.PAPER_ORIGIN_X - py,
                self.PAPER_ORIGIN_Y + px,
                pz)

    # ── 동작 시퀀스 ────────────────────────────────────────────────────────

    # 홈 이동 전 안전 Z 높이 (테이블면 기준, mm)
    SAFE_Z_CLEARANCE = 200.0

    def grip(self):
        R = self._R
        R['set_digital_output'](1, 0)
        R['set_digital_output'](2, 0)
        R['set_digital_output'](1, 1)
        R['wait'](1)

    def ungrip(self):
        R = self._R
        R['set_digital_output'](1, 0)
        R['set_digital_output'](2, 0)
        R['set_digital_output'](2, 1)
        R['wait'](1)

    def go_home(self):
        """홈 자세로 이동. 충돌 방지를 위해 먼저 Z를 올린 뒤 조인트 이동."""
        self._log.info("홈 위치로 이동")
        tcp = self._R['get_current_posx']()
        if tcp is not None:
            cx, cy = tcp[0][0], tcp[0][1]
            safe_z = self.PAPER_ORIGIN_Z + self.SAFE_Z_CLEARANCE
            self._R['movel'](self._posx(cx, cy, safe_z),
                             self.TRAVEL_VEL, self.TRAVEL_ACC)
        self._R['movej'](self._R['posj'](*self.HOME_JOINT), vel=40, acc=40)
        time.sleep(0.3)

    def detect_surface(self):
        """
        Compliance 제어를 이용해 도화지 표면 Z 좌표를 탐지합니다.

        Returns:
            float: 측정된 표면 Z (mm). 탐지 실패 시 PAPER_ORIGIN_Z 반환.
        """
        R = self._R
        self._log.info("─── 종이 표면 탐지 시작 ───")

        # 탐지 시작 위치 (도화지 중앙 위쪽)
        cx = self.PAPER_ORIGIN_X - self.PAPER_HEIGHT_MM / 2
        cy = self.PAPER_ORIGIN_Y + self.PAPER_WIDTH_MM / 2
        start_z = self.PAPER_ORIGIN_Z + self.PROBE_START_OFFSET

        self._log.info(f"탐지 시작 위치로 이동: ({cx:.0f}, {cy:.0f}, {start_z:.0f})")
        R['movel'](self._posx(cx, cy, start_z), self.TRAVEL_VEL, self.TRAVEL_ACC)
        time.sleep(0.5)

        # Compliance ON: Z축 강성만 낮게 설정 (종이에 닿으면 힘이 발생)
        stiffness = [3000, 3000, 200, 200, 200, 200]
        R['task_compliance_ctrl'](stiffness)
        self._log.info(f"Compliance 제어 ON (Z 강성: {stiffness[2]})")
        time.sleep(0.3)

        # 아래로 천천히 비동기 이동 시작
        target_z = self.PAPER_ORIGIN_Z - 30.0  # 예상 표면보다 30mm 더 내려가도록
        R['amovel'](self._posx(cx, cy, target_z), self.PROBE_VEL, self.PROBE_ACC)

        # 힘을 모니터링하며 접촉 감지
        surface_z  = self.PAPER_ORIGIN_Z
        detected   = False
        timeout    = time.time() + 15.0
        last_log_t = time.time()

        while time.time() < timeout:
            force = R['get_tool_force']()
            if force is not None:
                fz = abs(force[2])
                if time.time() - last_log_t >= 0.5:  # 0.5초마다 출력
                    self._log.info(f"Fz = {fz:.2f} N")
                    last_log_t = time.time()
                if fz >= self.CONTACT_FORCE_Z:
                    tcp = R['get_current_posx']()
                    if tcp is not None:
                        surface_z = tcp[0][2]
                    detected = True
                    self._log.info(
                        f"종이 접촉 감지! Z = {surface_z:.2f} mm  (Fz = {fz:.2f} N)"
                    )
                    break
            time.sleep(0.01)

        if not detected:
            self._log.warning("표면 탐지 타임아웃 — PAPER_ORIGIN_Z 사용")

        R['release_compliance_ctrl']()
        self._log.info("Compliance 제어 OFF")

        # 탐지 후 hover 높이로 복귀
        R['movel'](self._posx(cx, cy, surface_z + self.HOVER_HEIGHT),
                   self.TRAVEL_VEL, self.TRAVEL_ACC)
        return surface_z

    # movesx() 한 번 호출로 넘길 수 있는 최대 웨이포인트 수 (DSR API 제한)
    _MOVESX_MAX_PTS = 50

    def execute_path(self, path, surface_z):
        """
        글씨 경로를 실행합니다.

        획(PEN_DOWN 연속 구간)은 movesx()로 스플라인 이동해 부드럽게 그리고,
        획 사이 공이동(PEN_UP)은 movel()로 빠르게 이동합니다.

        Args:
            path:      PathGenerator.generate() 반환값
                       list of (x_mm, y_mm, pen_down)
            surface_z: detect_surface() 로 구한 표면 Z (mm)
        """
        R       = self._R
        hover_z = surface_z + self.HOVER_HEIGHT
        total   = len(path)
        stroke_count = 0

        self._log.info(
            f"─── 글씨 쓰기 시작 ───\n"
            f"  표면 Z:  {surface_z:.1f} mm\n"
            f"  이동 Z:  {hover_z:.1f} mm\n"
            f"  웨이포인트 수: {total}"
        )

        i = 0
        while i < total:
            px, py, pen_down = path[i]

            if not pen_down:
                # 공이동: hover 높이에서 movel()
                rx, ry, rz = self._paper_to_robot(px, py, hover_z)
                R['movel'](self._posx(rx, ry, rz), self.TRAVEL_VEL, self.TRAVEL_ACC)
                i += 1
            else:
                # 획 시작: 연속 PEN_DOWN 포인트를 모아 movesx() 호출
                stroke_pts = []
                while i < total and path[i][2] == PEN_DOWN:
                    bx, by, _ = path[i]
                    rx, ry, rz = self._paper_to_robot(bx, by, surface_z)
                    stroke_pts.append(self._posx(rx, ry, rz))
                    i += 1

                # DSR movesx() 최대 포인트 수 초과 시 분할 실행
                for chunk_start in range(0, len(stroke_pts), self._MOVESX_MAX_PTS):
                    chunk = stroke_pts[chunk_start:chunk_start + self._MOVESX_MAX_PTS]
                    if len(chunk) == 1:
                        R['movel'](chunk[0], self.WRITE_VEL, self.WRITE_ACC)
                    else:
                        R['movesx'](chunk, self.WRITE_VEL, self.WRITE_ACC)

                stroke_count += 1
                pct = 100 * i // total
                self._log.info(f"  획 {stroke_count} 완료  ({pct}%  {i}/{total})")

        self._log.info("─── 글씨 쓰기 완료 ───")


def main(args=None):
    rclpy.init(args=args)
    node = rclpy.create_node('cobot_writing_node', namespace=ROBOT_ID)
    DR_init.__dsr__node = node
    log = node.get_logger()

    # ── ROS2 파라미터 ────────────────────────────────────────────────────
    node.declare_parameter('text',                 'Hello World')
    node.declare_parameter('font_name',            'regular')
    node.declare_parameter('char_height_mm',       15.0)
    node.declare_parameter('paper_width_mm',       WritingNode.PAPER_WIDTH_MM)
    node.declare_parameter('paper_height_mm',      WritingNode.PAPER_HEIGHT_MM)
    node.declare_parameter('margin_mm',            25.0)
    node.declare_parameter('skip_surface_detect',  False)

    text            = node.get_parameter('text').value
    font_name       = node.get_parameter('font_name').value
    char_height_mm  = node.get_parameter('char_height_mm').value
    paper_width_mm  = node.get_parameter('paper_width_mm').value
    paper_height_mm = node.get_parameter('paper_height_mm').value
    margin_mm       = node.get_parameter('margin_mm').value
    skip_detect     = node.get_parameter('skip_surface_detect').value
    # ─────────────────────────────────────────────────────────────────────

    writer = WritingNode(log)
    try:
        writer.init_api()
    except ImportError as e:
        log.error(f"DSR_ROBOT2 import 실패: {e}")
        log.error("ws_dsr workspace를 source한 후 다시 실행하세요.")
        log.error("  source /home/dongmin/ws_cobot_pjt/ws_dsr/install/setup.bash")
        rclpy.shutdown()
        return

    # ── 경로 생성 ────────────────────────────────────────────────────────
    gen = PathGenerator(
        font_name=font_name,
        char_height_mm=char_height_mm,
        paper_width_mm=paper_width_mm,
        paper_height_mm=paper_height_mm,
        margin_mm=margin_mm,
    )
    path = gen.generate(text)
    log.info(f"문구: {repr(text)}\n{gen.summary(path)}")
    # ─────────────────────────────────────────────────────────────────────

    try:
        writer.go_home()

        if skip_detect:
            surface_z = WritingNode.PAPER_ORIGIN_Z
            log.info(f"표면 탐지 스킵 — Z = {surface_z:.1f} mm 사용")
        else:
            surface_z = writer.detect_surface()

        writer.execute_path(path, surface_z)
        writer.go_home()

    except KeyboardInterrupt:
        log.info("사용자 중단 (Ctrl+C)")
    except Exception as e:
        log.error(f"오류 발생: {e}")
        raise
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
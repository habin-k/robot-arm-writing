"""
writer.py — 붓펜 힘제어 글씨 쓰기 엔진.

PenWriter는 웨이포인트를 받아 표면 접촉 높이를 감지하고, 힘 제어를 적용해
붓펜으로 글씨를 쓰는 모션을 수행한다.

task_manager_node.py에서 import해 사용하며, 단독 실행 시에는 /robot/target_moving
토픽을 구독해 그리기 동작만 검증할 수 있다. DSR_ROBOT2 import 전에
DR_init.__dsr__node가 설정되어 있어야 한다.
"""

import queue
import threading
import time

import numpy as np
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

# 좌표 기준: 웨이포인트의 x,y,z(및 FORCE_ON_Z·접촉 z)는 BASE 가 아니라
# 사용자 좌표계(User Coordinates id 102) 기준이다. init 에서 set_ref_coord(USER_COORD_ID)
# 로 전역 기본 좌표를 이 좌표계로 바꿔, 모든 movel/movesx/get_current_posx/get_tool_force
# 가 이 프레임으로 동작하게 한다. (DSR user 좌표 유효 범위 101~200)
USER_COORD_ID = 102

# 힘 제어 글쓰기 설정. 웨이포인트는 x/y와 pen_down만 담고,
# 실제 z 높이는 각 획 시작 시 표면 접촉 감지로 결정한다.
FORCE_ON_Z        = 100     # 위치제어로 하강할 목표 z & 순응+힘제어를 켜는 높이 (BASE, mm)
                            # 실제 접촉 높이보다 높게 잡아야 위치제어 하강 중 종이를 누르지 않는다.
HOVER_HEIGHT      = 30.0    # 획 그린 뒤 올리는 높이 & 공이동 hover 높이 (mm)
HOVER_Z           = FORCE_ON_Z + HOVER_HEIGHT
SAFE_Z_CLEARANCE  = 200.0   # 홈 복귀 전 안전하게 들어올릴 높이 (FORCE_ON_Z 기준)

WRITE_FORCE_Z    = -3                          # 목표 힘 3N (음수 = 아래 방향)
WRITE_FORCE_DIR  = [0, 0, 1, 0, 0, 0]            # Z축 방향
WRITE_STIFFNESS  = [3000, 3000, 3000, 200, 200, 200]  # X/Y 강성 높게, Z 낮게

# 접촉 감지: 순응+힘제어로 하강 중, Z 외력이 이 값을 넘으면 '바닥 접촉'으로 판단하고
#            하강 대기를 끝낸다. 접촉 감지 후에는 순응/힘 제어를 끄고 위치제어로 그린다.
CONTACT_FORCE_N   = 2.4       # N (기본 바닥 접촉 판단 힘)
CONTACT_DEBOUNCE  = 5         # |Fz|가 임계를 '연속 이 횟수'(×0.01s=0.05s) 넘어야 접촉 확정 (노이즈 스파이크 무시)

WRITE_VEL  = [270.0,  270.0]    # 글씨 쓰기
WRITE_ACC  = [180.0, 180.0]
TRAVEL_VEL = [160.0, 120.0]    # 공이동 (빠름)
TRAVEL_ACC = [200.0, 160.0]
PROBE_VEL  = [8.0, 8.0]      # 표면 접근 (매우 느림)
PROBE_ACC  = [15.0, 15.0]

MOVESX_MAX_PTS = 50          # movesx 한 번에 넘길 수 있는 최대 포인트 수 (DSR 제한)


def _zyz_to_matrix(a_deg, b_deg, c_deg):
    """DSR 자세 표기(ZYZ 오일러, deg) → 3x3 회전행렬 R = Rz(a)·Ry(b)·Rz(c)."""
    a, b, c = np.radians([a_deg, b_deg, c_deg])
    ca, sa = np.cos(a), np.sin(a)
    cb, sb = np.cos(b), np.sin(b)
    cc, sc = np.cos(c), np.sin(c)
    Rz_a = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])
    Ry_b = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    Rz_c = np.array([[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]])
    return Rz_a @ Ry_b @ Rz_c


def _user_rotation_from_base(worker, user_id):
    """User 좌표계(user_id) 정의를 조회해 'BASE 벡터 → User 벡터' 회전행렬을 반환.
    실패 시 단위행렬(=BASE 그대로 표시)로 폴백한다."""
    try:
        conv, ref = worker.get_user_cart_coord(user_id)
        if ref != worker.DR_BASE:
            worker.log.warning(
                f"User_{user_id} 기준 ref={ref} (BASE 아님) — 외력 변환이 부정확할 수 있음")
        a, b, c = float(conv[3]), float(conv[4]), float(conv[5])
        R_base_from_user = _zyz_to_matrix(a, b, c)
        worker.log.info(
            f"User_{user_id} 외력 변환행렬 준비 (자세 abc = {a:.1f}, {b:.1f}, {c:.1f} deg)")
        return R_base_from_user.T   # v_user = R^T · v_base
    except Exception as e:
        worker.log.warning(f"User 좌표 변환행렬 조회 실패 — 외력을 BASE 로 표시: {e}")
        return np.eye(3)


class PenWriter:
    """
    붓펜 힘제어 글씨 쓰기 엔진.

    상태/좌표/외력/진행률은 생성자에 전달된 ROS 노드로 발행한다.
    비상정지는 공유 상태 dict의 `state['emergency']` 플래그로 전달받는다.
    """

    # 실시간 좌표·외력 발행 주기 (초). 쓰는 도중 폴링에서도 이 주기로 throttle.
    POSE_PUBLISH_INTERVAL = 0.1

    def __init__(self, node: Node, state: dict, *, init_robot: bool = True):
        """
        node       : publisher 를 붙이고 logger 를 쓸 rclpy 노드
        state      : {'emergency': bool, ...} 공유 딕셔너리 (비상정지 플래그를 읽음)
        init_robot : True 면 자율모드/Tool/TCP/기준좌표까지 설정한다 (단독 실행용).
                     task_manager 처럼 호출자가 Tool/TCP 를 이미 관리하면 False 로 넘겨
                     좌표 기준(set_ref_coord)만 맞추게 한다.
        """
        self.node  = node
        self.state = state
        self.log   = node.get_logger()

        # HMI와 서버가 구독하는 상태/좌표/외력/진행률 토픽.
        self.status_pub   = node.create_publisher(String,             '/robot/status', 10)
        self.pose_pub     = node.create_publisher(Float32MultiArray,  '/robot/current_pose', 10)
        self.force_pub    = node.create_publisher(Float32MultiArray,  '/robot/force', 10)
        # BASE 좌표계 좌표·외력 (HMI 에서 User_102 / BASE 선택 표시용)
        self.pose_base_pub  = node.create_publisher(Float32MultiArray, '/robot/current_pose_base', 10)
        self.force_base_pub = node.create_publisher(Float32MultiArray, '/robot/force_base', 10)
        self.progress_pub = node.create_publisher(Float32MultiArray,  '/robot/progress', 10)

        from DSR_ROBOT2 import (
            movel, movej, movesx, amovel, amovesx, check_motion,
            posx, posj, get_current_posx, get_user_cart_coord, set_robot_mode,
            set_ref_coord,
            task_compliance_ctrl, release_compliance_ctrl,
            set_desired_force, release_force, wait,
            check_force_condition, get_tool_force,
            set_tool, set_tcp, set_digital_output,
            DR_FC_MOD_ABS, DR_AXIS_Z, DR_BASE, DR_FC_MOD_REL
        )
        from DRFC import ROBOT_MODE_AUTONOMOUS

        self.movel  = movel
        self.movej  = movej
        self.movesx = movesx
        self.amovel  = amovel      # 비동기 직선 이동 (블로킹 X → 폴링하며 힘 발행)
        self.amovesx = amovesx     # 비동기 스플라인 이동
        self.check_motion = check_motion  # 0=모션 없음(완료), !=0=이동 중
        self.posx   = posx
        self.posj   = posj
        self.get_current_posx    = get_current_posx
        self.get_user_cart_coord = get_user_cart_coord
        self.set_digital_output  = set_digital_output

        # 힘/순응 제어 함수
        self.task_compliance_ctrl    = task_compliance_ctrl
        self.release_compliance_ctrl = release_compliance_ctrl
        self.set_desired_force       = set_desired_force
        self.release_force           = release_force
        self.check_force_condition   = check_force_condition
        self.get_tool_force          = get_tool_force
        self.wait                    = wait
        self.DR_FC_MOD_ABS           = DR_FC_MOD_ABS
        self.DR_FC_MOD_REL           = DR_FC_MOD_REL
        self.DR_AXIS_Z               = DR_AXIS_Z
        self.DR_BASE                 = DR_BASE

        self.set_ref_coord = set_ref_coord

        if init_robot:
            set_robot_mode(ROBOT_MODE_AUTONOMOUS)
            set_tool("Tool Weight")
            set_tcp("GripperDA_v1")
            set_ref_coord(USER_COORD_ID)
            self.log.info(f"DSR 자율 모드/Tool/TCP/기준좌표(User {USER_COORD_ID}) 설정 완료")
        # task_manager 통합 모드에서는 집기/도장(BASE 좌표)과 충돌하지 않도록
        # draw() 실행 구간에서만 User_102 좌표계를 사용한다.

        # get_tool_force 는 BASE/TOOL/WORLD 만 지원하므로, User_102 외력을 얻으려면
        # BASE 외력을 직접 회전 변환해야 한다. User_102 정의를 1회 조회해 회전행렬을 캐시한다.
        #   v_user = R_base_from_user^T · v_base
        self._R_bu = _user_rotation_from_base(self, USER_COORD_ID)

        self._last_pose_t = 0.0
        self._contact_z   = None
        # 바닥 접촉 판단 힘(N). 기본은 모듈 상수, 펜 종류에 따라 set_contact_force 로 교체.
        #   (task_manager 가 선택 펜의 접촉힘을 draw 전에 넣어 준다.)
        self.contact_force = CONTACT_FORCE_N

        # HMI 관리자 파라미터로 런타임 갱신되는 모션 설정.
        self.write_vel    = list(WRITE_VEL)
        self.write_acc    = list(WRITE_ACC)
        self.travel_vel   = list(TRAVEL_VEL)
        self.travel_acc   = list(TRAVEL_ACC)
        self.write_force_z = WRITE_FORCE_Z
        self.force_on_z    = FORCE_ON_Z    # 위치제어 하강 목표 z & 순응+힘제어 켜는 높이

    def publish_status(self, s):
        self.status_pub.publish(String(data=s))

    _status = publish_status

    def publish_no_paper(self):
        """종이 미감지로 작업을 시작하지 못했음을 HMI에 알린다."""
        self.publish_status("NO_PAPER")

    def _progress(self, done, total):
        """획 진행 발행 [완료 획 수, 전체 획 수]."""
        msg = Float32MultiArray()
        msg.data = [float(done), float(total)]
        self.progress_pub.publish(msg)

    def _log_zf(self, tag):
        """디버깅용: 현재 z(User_102, mm)와 Z축 외력 Fz(N)를 터미널에 출력."""
        try:
            z  = self.get_current_posx()[0][2]
            fz = self.get_tool_force(ref=self.DR_BASE)[2]
            self.log.info(f"  [{tag}]  z = {z:7.2f} mm   Fz = {fz:+6.2f} N")
        except Exception as e:
            self.log.warning(f"  [{tag}] z/Fz 읽기 실패: {e}")

    def _force_user102(self):
        """현재 TCP 외력을 User_102 기준 [fx,fy,fz,tx,ty,tz] 로 반환.
        get_tool_force 는 BASE 만 지원하므로 BASE 외력을 회전행렬로 User_102 로 변환한다."""
        f = self.get_tool_force(ref=self.DR_BASE)
        if not isinstance(f, (list, tuple)) or len(f) < 6:
            return None
        fb = np.array(f[:3], dtype=float)   # 병진 힘 (BASE)
        tb = np.array(f[3:6], dtype=float)  # 토크 (BASE)
        fu = self._R_bu @ fb
        tu = self._R_bu @ tb
        return [float(v) for v in (*fu, *tu)]

    def publish_live(self, force=True):
        """현재 TCP 좌표·외력(User_102 기준)을 /robot/current_pose·/robot/force 로 발행.
        throttle O — 유휴/조그뿐 아니라 쓰는 도중(async 모션 폴링)에도 호출되어 실시간 갱신된다."""
        now = time.time()
        if now - self._last_pose_t < self.POSE_PUBLISH_INTERVAL:
            return
        self._last_pose_t = now

        # 현재 좌표 — User_102 & BASE 둘 다 발행 (HMI 에서 좌표계 선택)
        try:
            res = self.get_current_posx(ref=USER_COORD_ID)
            if res is not None and res[0] is not None:
                msg = Float32MultiArray()
                msg.data = [float(v) for v in res[0][:6]]
                self.pose_pub.publish(msg)
        except Exception as e:
            self.log.warning(f"좌표 발행 실패(User_102): {e}")
        try:
            resb = self.get_current_posx(ref=self.DR_BASE)
            if resb is not None and resb[0] is not None:
                msgb = Float32MultiArray()
                msgb.data = [float(v) for v in resb[0][:6]]
                self.pose_base_pub.publish(msgb)
        except Exception as e:
            self.log.warning(f"좌표 발행 실패(BASE): {e}")

        # 현재 TCP 외력 — User_102 & BASE 둘 다 발행 [fx,fy,fz,tx,ty,tz]
        if force:
            try:
                fu = self._force_user102()
                if fu is not None:
                    fmsg = Float32MultiArray()
                    fmsg.data = fu
                    self.force_pub.publish(fmsg)
            except Exception as e:
                self.log.warning(f"외력 발행 실패(User_102): {e}")
            try:
                fb = self.get_tool_force(ref=self.DR_BASE)
                if isinstance(fb, (list, tuple)) and len(fb) >= 6:
                    fbmsg = Float32MultiArray()
                    fbmsg.data = [float(v) for v in fb[:6]]
                    self.force_base_pub.publish(fbmsg)
            except Exception as e:
                self.log.warning(f"외력 발행 실패(BASE): {e}")

    _publish_live = publish_live

    def _enable_write_force(self):
        """순응 제어 + 목표 힘(-3N) ON — 붓을 종이에 일정 힘으로 누른다."""
        fd = [0, 0, self.write_force_z, 0, 0, 0]
        self.task_compliance_ctrl(WRITE_STIFFNESS)
        self.wait(0.1)
        self.set_desired_force(fd, dir=WRITE_FORCE_DIR, mod=self.DR_FC_MOD_REL)

    def _disable_write_force(self):
        """힘 제어 → 순응 제어 순서로 반드시 해제한다."""
        self.release_force()
        self.wait(0.1)
        self.release_compliance_ctrl()

    def _wait_motion_done(self, poll=0.03):
        """async 모션(amovel/amovesx)이 끝날 때까지 폴링하며 좌표·외력을 실시간 발행한다.
        비상정지가 걸리면 즉시 반환한다. (단일 스레드 폴링 — DSR 노드 spin 충돌 없음)"""
        self.wait(0.08)   # 모션이 큐에 올라가 check_motion 이 !=0 이 될 시간 확보
        while True:
            if self.state.get('emergency'):
                return
            try:
                if self.check_motion() == 0:   # 0 = 모션 없음(완료)
                    break
            except Exception:
                break
            self.publish_live()
            self.wait(poll)

    def set_contact_force(self, force_n):
        """바닥 접촉 판단 힘(N)을 교체한다. task_manager 가 선택 펜(빨강 2.4 / 얇은 펜 1.8)에
        맞춰 draw() 호출 전에 넣어 준다."""
        self.contact_force = float(force_n)
        self.log.info(f"접촉 판단 힘 설정: {self.contact_force:.2f} N")

    def apply_tuning(self, params: dict):
        """HMI 관리자탭에서 보낸 모션 파라미터를 실시간 반영한다.
        params 예: {'write_vel':[..], 'write_acc':[..], 'travel_vel':[..],
                   'travel_acc':[..], 'write_force_z': -3}. 없는 키는 현재값을 유지한다."""
        def _vel2(key, cur):
            v = params.get(key)
            try:
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    return [float(v[0]), float(v[1])]
            except (TypeError, ValueError):
                pass
            return cur
        self.write_vel     = _vel2('write_vel',  self.write_vel)
        self.write_acc     = _vel2('write_acc',  self.write_acc)
        self.travel_vel    = _vel2('travel_vel', self.travel_vel)
        self.travel_acc    = _vel2('travel_acc', self.travel_acc)
        for key in ('write_force_z', 'force_on_z'):
            if key in params:
                try:
                    setattr(self, key, float(params[key]))
                except (TypeError, ValueError):
                    pass
        self.log.info(
            f"모션 파라미터 갱신: write_vel={self.write_vel} write_acc={self.write_acc} "
            f"travel_vel={self.travel_vel} travel_acc={self.travel_acc} "
            f"write_force_z={self.write_force_z} force_on_z={self.force_on_z}")

    def _wait_for_contact(self):
        """
        순응+힘제어로 하강하는 동안 get_tool_force 로 Z 외력을 감시해 바닥 접촉을 감지한다.

        Z 외력이 임계값을 연속 CONTACT_DEBOUNCE회 넘을 때만 접촉으로 확정한다.
        접촉 확정 시점의 z(mm)를 반환한다.
        """
        hits = 0
        contact_z = self.force_on_z
        while True:
            if self.state.get('emergency'):
                self.log.warning("비상정지 — 접촉 대기 중단")
                break
            try:
                fz = self.get_tool_force(ref=self.DR_BASE)[2]
                pz = self.get_current_posx()[0][2]
            except Exception:
                self.wait(0.01)
                continue

            hits = hits + 1 if abs(fz) >= self.contact_force else 0
            self.log.info(f"    하강 중  Fz = {fz:+.2f} N   z = {pz:.2f} mm   "
                          f"(임계 {self.contact_force} N, 연속 {hits}/{CONTACT_DEBOUNCE})")

            if hits >= CONTACT_DEBOUNCE:
                contact_z = pz
                self.log.info(f"바닥 접촉 확정 — z = {contact_z:.2f} mm,  Fz = {fz:+.2f} N")
                break
            self.publish_live()   # 접촉 감지 하강 중에도 좌표·외력 실시간 발행
            self.wait(0.01)
        return contact_z

    @staticmethod
    def _split_strokes(data):
        """flat 웨이포인트(7값×N)를 pen_down 연속 구간별 획으로 묶는다.
        반환: [[(x, y, rx, ry, rz), ...], ...]  (pen_up 점은 버림 — 접근은 획 시작에서 처리)"""
        strokes, cur = [], []
        for i in range(0, len(data) - 6, 7):
            x, y, _z, rx, ry, rz, pen = data[i:i + 7]
            if int(pen):
                cur.append((x, y, rx, ry, rz))
            elif cur:
                strokes.append(cur)
                cur = []
        if cur:
            strokes.append(cur)
        return strokes

    def _draw_stroke(self, stroke):
        """한 획을 그린다.
          1.  시작점 위 hover 이동
          2.  접촉 z 결정:
                · 첫 획      → FORCE_ON_Z 까지 하강 후 순응+힘제어로 접촉 감지, z 를 self._contact_z 에 저장
                · 이후 획    → 저장된 self._contact_z 로 곧장 위치제어 하강 (힘 감지 생략)
          3.  접촉 z 에서 위치제어(movesx)로 획 그리기 (Z 고정)
          4.  30mm 상승"""
        fx, fy, frx, fry, frz = stroke[0]     # 시작점
        lx, ly, lrx, lry, lrz = stroke[-1]    # 끝점

        # 이 획을 어디로 그리라고 명령하는지 출력 (겹침 문제 진단용)
        self.log.info(f"  ▶ 획 시작 목표  X={fx:.1f}  Y={fy:.1f}   ({len(stroke)}점)")
        before = self.get_current_posx()
        if before is not None and before[0] is not None:
            self.log.info(f"     이동 전 실제  X={before[0][0]:.1f}  Y={before[0][1]:.1f}")

        self.movel(self.posx(fx, fy, self.force_on_z + HOVER_HEIGHT, frx, fry, frz), vel=self.travel_vel, acc=self.travel_acc)
        after = self.get_current_posx()
        if after is not None and after[0] is not None:
            self.log.info(f"     hover 이동 후 실제  X={after[0][0]:.1f}  Y={after[0][1]:.1f}")

        # 첫 획에서만 힘/순응 제어로 종이 접촉 z 를 감지해 메모리(self._contact_z)에 저장하고,
        # 이후 획들은 그 z 로 곧장 위치제어 하강한다 (획마다 힘 감지 반복 제거 → 빠름).
        # 전제: User_102 의 XY 평면이 종이면과 평행 → 접촉 z 가 쓰기 영역 전체에서 일정하다.
        if self._contact_z is None:
            self.movel(self.posx(fx, fy, self.force_on_z, frx, fry, frz), vel=PROBE_VEL, acc=PROBE_ACC)
            self.wait(0.2)
            self._log_zf("힘제어 ON 직전")
            self._enable_write_force()
            self._contact_z = self._wait_for_contact()
            self._disable_write_force()   # 접촉 감지 직후 순응+힘 제어 OFF
            self.log.info(f"     접촉 z 저장 = {self._contact_z:7.2f} mm  "
                          f"(이후 획은 힘 감지 없이 이 z 로 위치제어 하강)")
        else:
            # 저장된 z 로 천천히(위치제어) 하강 — 힘/순응 제어 없음
            self.movel(self.posx(fx, fy, self._contact_z, frx, fry, frz),
                       vel=PROBE_VEL, acc=PROBE_ACC)
            self.log.info(f"     저장된 접촉 z = {self._contact_z:7.2f} mm 로 위치제어 하강")

        contact_z = self._contact_z

        # 접촉 z 에서 '위치 제어'로 획 그리기 (순응/힘 제어 없음, Z 고정).
        # 블로킹 movesx 대신 async(amovesx)+폴링으로 실행 → 쓰는 동안에도 좌표·외력을 실시간 발행.
        path = [self.posx(x, y, contact_z, rx, ry, rz) for x, y, rx, ry, rz in stroke]
        for s in range(0, len(path), MOVESX_MAX_PTS):
            if self.state.get('emergency'):
                return
            chunk = path[s:s + MOVESX_MAX_PTS]
            if len(chunk) == 1:
                self.amovel(chunk[0], vel=self.write_vel, acc=self.write_acc)
            else:
                self.amovesx(chunk, vel=self.write_vel, acc=self.write_acc)
            self._wait_motion_done()   # 이동 완료까지 폴링하며 pose/force 발행
            # 그리는 동안 붓이 잘 눌리는지(=종이 평탄도) 확인: 위치제어라 힘은 '측정'만 됨
            self._log_zf(f"그리는 중 {min(s + MOVESX_MAX_PTS, len(path))}/{len(path)}점")

        self.movel(self.posx(lx, ly, contact_z + HOVER_HEIGHT, lrx, lry, lrz),
                   vel=self.travel_vel, acc=self.travel_acc)

    def draw(self, waypoints):
        """
        웨이포인트(flat 7값×N)를 힘 제어로 실행한다.  홈 복귀 → 획들 실행 → 홈 복귀.

        블로킹 — 다 그리면 리턴한다. 비상정지(state['emergency'])가 걸리면 중단하고
        ERROR 상태를 발행한 뒤 리턴한다.
        task_manager 의 write() 에서 이 메서드를 호출한다.
        """
        strokes = self._split_strokes(waypoints)   # pen_down 연속 구간을 획으로 묶음
        if not strokes:
            self.publish_status("IDLE")
            self.log.warning("웨이포인트가 비어 있음")
            return

        self.log.info("글쓰기 시작")
        self.publish_status("WRITING")

        # 글쓰기 구간에서만 User_102 좌표계를 사용하고, 끝나면 BASE로 복원한다.
        self.set_ref_coord(USER_COORD_ID)
        try:
            self._draw_strokes(strokes)
        finally:
            self.set_ref_coord(self.DR_BASE)

    def _draw_strokes(self, strokes):
        """draw() 의 실제 획 실행 루프 (전역 기준 좌표=User_102 인 상태에서 호출)."""
        total = len(strokes)
        self._progress(0, total)               # 시작 시 전체 획 수 알림 (진행바 0%)

        self._contact_z = None                 # 새 작업마다 접촉 z 재감지 (종이가 바뀌었을 수 있음)
        for n, stroke in enumerate(strokes, 1):
            if self.state.get('emergency'):
                self.log.warning("비상정지로 글쓰기 중단")
                self.publish_status("ERROR")
                return
            self._draw_stroke(stroke)
            self.publish_live()
            self._progress(n, total)           # 획 완료마다 진행 갱신
            self.log.info(f"  획 {n}/{total} 완료")

        self.publish_status("IDLE")
        self.log.info("글쓰기 완료")

    def _go_home(self):
        """현재 위치에서 안전 높이로 수직 상승한 뒤 홈 관절 자세로 이동한다."""
        self.log.info("홈 위치로 이동")
        res = self.get_current_posx()
        if res is not None and res[0] is not None:
            cx, cy, cz, crx, cry, crz = res[0][:6]
            safe_z = max(cz, self.force_on_z + SAFE_Z_CLEARANCE)  # 아래로는 안 내려감
            self.movel(self.posx(cx, cy, safe_z, crx, cry, crz),
                       vel=self.travel_vel, acc=self.travel_acc)
        self.movej(self.posj(*HOME_JOINT), vel=10, acc=10)
        self.wait(0.3)
        self.publish_live()   # 홈 복귀 후 좌표 갱신

    def home(self):
        """공개 홈 복귀 (HOMING → IDLE 상태 발행)."""
        self.log.info("원점 복귀")
        self.publish_status("HOMING")
        self._go_home()
        self.publish_status("IDLE")
        self.log.info("원점 복귀 완료")

    def _do_grip(self):
        """그리퍼 집기 (digital output 1)."""
        self.log.info("그립")
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(1, 1)
        self.wait(1)

    def _do_ungrip(self):
        """그리퍼 놓기 (digital output 2)."""
        self.log.info("언그립")
        self.set_digital_output(1, 0)
        self.set_digital_output(2, 0)
        self.set_digital_output(2, 1)
        self.wait(1)

    def run(self, cmd_queue: queue.Queue):
        """메인 스레드에서 큐를 소비하며 모션을 실행한다. (단독 실행용)
        task_manager 통합 시에는 이 루프 대신 draw()/home() 을 직접 호출한다."""
        while rclpy.ok():
            if cmd_queue.empty():
                self.publish_live()
                time.sleep(0.05)
                continue

            cmd, data = cmd_queue.get()
            self.state['busy'] = True
            if   cmd == 'write':  self.draw(data)
            elif cmd == 'home':   self.home()
            elif cmd == 'reset':  self._do_reset()
            elif cmd == 'grip':   self._do_grip()
            elif cmd == 'ungrip': self._do_ungrip()
            self.state['busy'] = False

    def _do_reset(self):
        self.log.info("에러 리셋")
        from DSR_ROBOT2 import set_robot_mode
        from DRFC import ROBOT_MODE_AUTONOMOUS
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
        self.state['emergency'] = False
        self.publish_status("IDLE")


class _CommandNode(Node):
    """
    PenWriter 단독 실행용 명령 구독 노드.
    콜백은 명령을 큐에 넣기만 하고 실제 모션은 실행하지 않는다.
    발행자(status/pose/force/progress)는 PenWriter 가 소유하므로 여기엔 없다.
    """

    def __init__(self, cmd_queue: queue.Queue, state: dict):
        super().__init__('controller_node', namespace=ROBOT_ID)
        self.q      = cmd_queue
        self.state  = state
        self.writer = None   # main() 에서 PenWriter 생성 후 주입 (estop 상태 발행용)

        # 비상정지용 move_stop 서비스 클라이언트 (진행 중인 모션을 즉시 중단)
        self.move_stop_cli = self.create_client(MoveStop, f'/{ROBOT_ID}/motion/move_stop')
        # 연속 조그용 jog 서비스 클라이언트 (누르면 속도 지정, 떼면 속도 0)
        self.jog_cli       = self.create_client(Jog, f'/{ROBOT_ID}/motion/jog')

        self.create_subscription(Float32MultiArray, '/robot/target_moving', self._on_moving, 10)
        self.create_subscription(Bool,              '/safety/emergency_stop', self._on_estop, 10)
        self.create_subscription(Bool,              '/robot/go_home',         self._on_home, 10)
        self.create_subscription(Bool,              '/robot/error_reset',     self._on_reset, 10)
        self.create_subscription(Float32MultiArray, '/robot/jog',             self._on_jog, 10)
        self.create_subscription(Bool,              '/robot/grip',            self._on_grip, 10)

        self.get_logger().info("통신 노드 준비 완료 (writer 단독 실행)")

    def _on_moving(self, msg):
        self.state['emergency'] = False
        self.q.put(('write', list(msg.data)))

    def _on_estop(self, msg):
        if msg.data:
            self.state['emergency'] = True  # 진행 중인 글쓰기 루프 중단용 플래그
            req = MoveStop.Request()
            req.stop_mode = DR_QSTOP
            self.move_stop_cli.call_async(req)  # fire-and-forget
            if self.writer is not None:
                self.writer.publish_status("ERROR")
            self.get_logger().error("비상정지 수신 — 로봇 정지 명령 전송")

    def _on_home(self, msg):
        if msg.data:
            self.q.put(('home', None))

    def _on_reset(self, msg):
        if msg.data:
            self.q.put(('reset', None))

    def _on_grip(self, msg):
        self.q.put(('grip' if msg.data else 'ungrip', None))

    def _on_jog(self, msg):
        if len(msg.data) < 2:
            return
        axis_idx = int(msg.data[0])
        speed    = float(msg.data[1])
        req = Jog.Request()
        req.jog_axis       = JOG_AXIS_TASK_X + axis_idx
        req.move_reference = DR_BASE_REF
        req.speed          = speed
        self.jog_cli.call_async(req)  # fire-and-forget


def main(args=None):
    """PenWriter 단독 실행 진입점."""
    rclpy.init(args=args)

    cmd_queue = queue.Queue()
    state = {'emergency': False, 'busy': False}

    # 1) DSR 전용 노드 — DSR 함수가 내부적으로만 spin. 우리가 spin 하지 않는다.
    dsr_node = rclpy.create_node('dsr_motion', namespace=ROBOT_ID)
    DR_init.__dsr__id    = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL
    DR_init.__dsr__node  = dsr_node

    # 2) 명령 구독 노드 — 전용 executor 로 백그라운드 스레드에서 spin
    sub_node = _CommandNode(cmd_queue, state)
    sub_exec = SingleThreadedExecutor()
    sub_exec.add_node(sub_node)
    spin_thread = threading.Thread(target=sub_exec.spin, daemon=True)
    spin_thread.start()

    # 3) 메인 스레드에서 그리기 엔진 실행 (DSR 함수 여기서만 호출)
    writer = PenWriter(sub_node, state, init_robot=True)  # 발행자는 sub_node 에 붙는다
    sub_node.writer = writer                              # estop 시 상태 발행용
    writer.run(cmd_queue)

    sub_node.destroy_node()
    dsr_node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

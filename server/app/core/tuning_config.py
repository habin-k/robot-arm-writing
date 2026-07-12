"""관리자 조절 파라미터 저장소 (HMI '파라미터 설정' 탭 백엔드).

두 종류의 파라미터를 서버 메모리에 보관하고 JSON 파일로 영속화한다.
  · motion : 로봇 모션 파라미터 → ros_node 가 /robot/tuning(JSON, latched)으로 발행 →
             task_manager(writer) 가 실시간 반영. 코드 수정/재빌드/재시작 불필요.
  · path   : 경로 생성 파라미터 → writing.py 가 PathGenerator 생성 시 주입 (서버 내부).

서버 재시작해도 유지되도록 set 시 파일로 저장하고, 시작 시 로드한다.
"""
import json
import os
import threading

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tuning_config.json")
_lock = threading.Lock()

# 로봇 모션 기본값 (writer.py / task_manager PENS 의 기본값과 동일해야 함)
DEFAULT_MOTION = {
    "write_vel":     [270.0, 270.0],   # 글씨 쓰기 속도 [일반, 회전]
    "write_acc":     [180.0, 180.0],   # 글씨 쓰기 가속
    "travel_vel":    [160.0, 120.0],   # 공이동 속도
    "travel_acc":    [200.0, 160.0],   # 공이동 가속
    "write_force_z": -3.0,             # 붓 누르는 목표 힘 (N, 음수=아래)
    "force_on_z":    100.0,            # 위치제어 하강 목표 z & 순응+힘제어 켜는 높이 (mm)
    "contact_force": {"red": 2.4, "purple": 1.8, "cyan": 1.8},  # 펜별 바닥 접촉 판단 힘 (N)
}

# 경로 생성 기본값 (PathGenerator 의 사용자-미지정 인자 + _CURVE_STEPS)
DEFAULT_PATH = {
    "line_spacing_factor": 1.6,      # 줄 간격 = char_height × factor
    "char_spacing_mm":     20.0,     # 글자 간 추가 간격 (mm)
    "paper_width_mm":      295.57,   # 도화지 가로 (mm)
    "paper_height_mm":     209.72,   # 도화지 세로 (mm)
    "hatch_spacing_mm":    1.0,      # 해칭(속채우기) 선 간격 (mm)
    "curve_steps":         12,       # 베지어 곡선 분해 세밀도 (_CURVE_STEPS)
}

_state = {
    "motion": json.loads(json.dumps(DEFAULT_MOTION)),
    "path":   json.loads(json.dumps(DEFAULT_PATH)),
}


def _save():
    try:
        with open(_PATH, "w") as f:
            json.dump(_state, f, indent=2, ensure_ascii=False)
    except OSError:
        pass  # 저장 실패해도 메모리 값으로 계속 동작


def _load():
    if not os.path.exists(_PATH):
        return
    try:
        with open(_PATH) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return
    # 기본값 위에 저장값을 덮어써 병합 (키 누락/추가에 안전)
    for grp in ("motion", "path"):
        for k, v in (saved.get(grp) or {}).items():
            if k in _state[grp]:
                if isinstance(_state[grp][k], dict) and isinstance(v, dict):
                    _state[grp][k].update(v)
                else:
                    _state[grp][k] = v


_load()


def get_motion() -> dict:
    with _lock:
        return json.loads(json.dumps(_state["motion"]))


def get_path() -> dict:
    with _lock:
        return json.loads(json.dumps(_state["path"]))


def set_motion(params: dict) -> dict:
    """모션 파라미터를 병합 저장하고 갱신된 전체 dict 를 반환한다."""
    with _lock:
        for k, v in params.items():
            if k not in _state["motion"]:
                continue
            if k == "contact_force" and isinstance(v, dict):
                for pen, val in v.items():
                    if pen in _state["motion"]["contact_force"]:
                        _state["motion"]["contact_force"][pen] = float(val)
            else:
                _state["motion"][k] = v
        _save()
        return json.loads(json.dumps(_state["motion"]))


def set_path(params: dict) -> dict:
    with _lock:
        for k, v in params.items():
            if k in _state["path"]:
                _state["path"][k] = v
        _save()
        return json.loads(json.dumps(_state["path"]))

from dataclasses import dataclass, field
from typing import Optional
import asyncio
import time

@dataclass
class JobState:
    job_id: Optional[str] = None
    status: str = "idle"          # idle / writing / done / error / cancelled
    progress_pct: int = 0
    current_stroke: int = 0
    total_strokes: int = 0
    current_char: str = ""
    error_msg: str = ""
    # 작업 경과 타이머용 (epoch 초). started_at=0 이면 미시작,
    # finished_at=0 이면 진행 중(끝나면 종료 시각 기록해 타이머 정지).
    started_at: float = 0.0
    finished_at: float = 0.0
    # 획 인덱스 → 글자 매핑 (execute 시 path_generator.stroke_char_map 으로 채움).
    # 서버 내부용 — progress_payload 에는 포함하지 않고 current_char 역추적에만 쓴다.
    stroke_chars: list = field(default_factory=list)

job_state = JobState()


@dataclass
class RobotLiveState:
    """HMI WebSocket으로 전달할 로봇 실시간 상태."""
    tcp_position: list = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])  # User_102 [x,y,z,rx,ry,rz]
    tcp_force: list = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])     # User_102 [fx,fy,fz,tx,ty,tz] (N, Nm)
    tcp_position_base: list = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])  # BASE [x,y,z,rx,ry,rz]
    tcp_force_base: list = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])      # BASE [fx,fy,fz,tx,ty,tz] (N, Nm)
    paper_present: Optional[bool] = None   # True=종이 있음, False=없음, None=미확인

robot_live = RobotLiveState()

# WebSocket 클라이언트 관리
progress_clients = set()
robot_clients = set()

# FastAPI 이벤트 루프 참조 (ROS 스레드에서 브로드캐스트를 예약하기 위함)
event_loop: Optional[asyncio.AbstractEventLoop] = None


def schedule_broadcast():
    """ROS 콜백(다른 스레드)에서 FastAPI 이벤트 루프에 브로드캐스트를 예약한다."""
    if event_loop is not None:
        asyncio.run_coroutine_threadsafe(broadcast_progress(), event_loop)


def job_elapsed_sec() -> int:
    """작업 시작 후 경과 초. 진행 중이면 현재까지, 끝났으면 종료 시점까지로 고정."""
    if job_state.started_at <= 0:
        return 0
    end = job_state.finished_at if job_state.finished_at > 0 else time.time()
    return max(0, int(end - job_state.started_at))


def progress_payload() -> dict:
    return {
        "job_id":        job_state.job_id,
        "status":        job_state.status,
        "progress_pct":  job_state.progress_pct,
        "current_stroke": job_state.current_stroke,
        "total_strokes": job_state.total_strokes,
        "current_char":  job_state.current_char,
        "error_msg":     job_state.error_msg,
        # 타이머: 서버 기준 경과 초 + 진행 여부. 클라이언트가 이 값을 기준으로 매초 로컬 틱.
        "elapsed_sec":   job_elapsed_sec(),
        "running":       job_state.started_at > 0 and job_state.finished_at == 0.0,
    }


async def broadcast_progress():
    if not progress_clients:
        return
    import json
    data = json.dumps(progress_payload())
    dead = set()
    for ws in progress_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    progress_clients -= dead


def robot_live_payload() -> dict:
    return {
        "tcp_position":      robot_live.tcp_position,
        "tcp_force":         robot_live.tcp_force,
        "tcp_position_base": robot_live.tcp_position_base,
        "tcp_force_base":    robot_live.tcp_force_base,
        "paper_present":     robot_live.paper_present,
    }


def schedule_robot_broadcast():
    """ROS 콜백(다른 스레드)에서 로봇 실시간 상태 브로드캐스트를 예약한다."""
    if event_loop is not None:
        asyncio.run_coroutine_threadsafe(broadcast_robot(), event_loop)


async def broadcast_robot():
    if not robot_clients:
        return
    import json
    data = json.dumps(robot_live_payload())
    dead = set()
    for ws in robot_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    robot_clients -= dead

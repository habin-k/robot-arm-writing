from dataclasses import dataclass, field
from typing import Optional
import asyncio

@dataclass
class JobState:
    job_id: Optional[str] = None
    status: str = "idle"          # idle / writing / done / error / cancelled
    progress_pct: int = 0
    current_stroke: int = 0
    total_strokes: int = 0
    current_char: str = ""
    error_msg: str = ""

job_state = JobState()

# WebSocket 클라이언트 관리
progress_clients: set = field(default_factory=set)
robot_clients: set = field(default_factory=set)

progress_clients = set()
robot_clients = set()


async def broadcast_progress():
    if not progress_clients:
        return
    data = {
        "job_id":        job_state.job_id,
        "status":        job_state.status,
        "progress_pct":  job_state.progress_pct,
        "current_stroke": job_state.current_stroke,
        "total_strokes": job_state.total_strokes,
        "current_char":  job_state.current_char,
        "error_msg":     job_state.error_msg,
    }
    import json
    dead = set()
    for ws in progress_clients:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            dead.add(ws)
    progress_clients -= dead

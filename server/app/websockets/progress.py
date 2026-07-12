import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.robot_state import progress_payload

router = APIRouter(tags=["WebSocket"])

# robot.py 와 동일한 이유로 '최신 상태 폴링' 방식으로 푸시한다.
# (진행률/상태가 바뀔 때마다 즉시, 안 바뀌어도 하트비트로 끊김 감지)
POLL_INTERVAL   = 0.1   # 초 (10Hz)
HEARTBEAT_EVERY = 20    # 변화 없어도 이 횟수(=2초)마다 1회 전송


@router.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await ws.accept()
    last = None
    idle = 0
    try:
        while True:
            payload = json.dumps(progress_payload())
            if payload != last or idle >= HEARTBEAT_EVERY:
                await ws.send_text(payload)
                last = payload
                idle = 0
            else:
                idle += 1
            await asyncio.sleep(POLL_INTERVAL)
    except (WebSocketDisconnect, Exception):
        pass

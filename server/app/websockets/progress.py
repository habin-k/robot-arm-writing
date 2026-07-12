import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.robot_state import progress_payload

router = APIRouter(tags=["WebSocket"])

# 최신 진행 상태를 폴링해 변경 시 즉시 전송하고, 주기적으로 하트비트를 보낸다.
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

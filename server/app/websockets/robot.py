import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.robot_state import robot_live_payload

router = APIRouter(tags=["WebSocket"])

# 서버 메모리의 최신 로봇 상태를 폴링해 변경 시 즉시 전송하고,
# 주기적으로 하트비트를 보내 연결 상태를 확인한다.
POLL_INTERVAL   = 0.1   # 초 (10Hz)
HEARTBEAT_EVERY = 20    # 변화가 없어도 이 횟수(=2초)마다 1회 전송 → 끊김 감지용


@router.websocket("/ws/robot")
async def ws_robot(ws: WebSocket):
    await ws.accept()
    last = None
    idle = 0
    try:
        while True:
            payload = json.dumps(robot_live_payload())
            # 값이 바뀌면 즉시, 안 바뀌어도 주기적으로(하트비트) 전송한다.
            if payload != last or idle >= HEARTBEAT_EVERY:
                await ws.send_text(payload)
                last = payload
                idle = 0
            else:
                idle += 1
            await asyncio.sleep(POLL_INTERVAL)
    except (WebSocketDisconnect, Exception):
        pass

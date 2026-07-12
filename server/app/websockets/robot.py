import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.robot_state import robot_live_payload

router = APIRouter(tags=["WebSocket"])

# 서버 메모리(robot_live)의 최신값을 이 주기로 폴링해 클라이언트로 직접 푸시한다.
# ROS 콜백(백그라운드 스레드)에서 run_coroutine_threadsafe 로 브로드캐스트를 예약하던
# 방식은 실시간 전달이 안 돼(연결 시 스냅샷 1회만 도착), 핸들러가 직접 최신값을 읽어
# 보내는 '최신 프레임 폴링' 방식으로 바꿨다. (좌표/외력이 20Hz로 갱신되므로 100ms 충분)
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

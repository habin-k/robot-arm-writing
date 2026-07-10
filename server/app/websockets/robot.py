import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.robot_state import robot_clients, robot_live_payload

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/robot")
async def ws_robot(ws: WebSocket):
    await ws.accept()
    robot_clients.add(ws)
    # 연결 직후 현재 상태 1회 전송 (다음 갱신 전까지 빈 화면 방지)
    try:
        await ws.send_text(json.dumps(robot_live_payload()))
    except Exception:
        pass
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        robot_clients.discard(ws)

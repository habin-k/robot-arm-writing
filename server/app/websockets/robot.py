from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.robot_state import robot_clients

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/robot")
async def ws_robot(ws: WebSocket):
    await ws.accept()
    robot_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        robot_clients.discard(ws)

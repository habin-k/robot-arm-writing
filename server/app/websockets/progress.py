from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.robot_state import progress_clients

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await ws.accept()
    progress_clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # 클라이언트 ping 유지용
    except WebSocketDisconnect:
        progress_clients.discard(ws)

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.robot_state import progress_clients, progress_payload

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await ws.accept()
    progress_clients.add(ws)
    # 연결 직후 현재 작업 상태 1회 전송 (새로고침/재접속 시 UI가 실제 상태를 반영)
    try:
        await ws.send_text(json.dumps(progress_payload()))
    except Exception:
        pass
    try:
        while True:
            await ws.receive_text()  # 클라이언트 ping 유지용
    except WebSocketDisconnect:
        progress_clients.discard(ws)

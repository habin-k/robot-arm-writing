import sys
import time
import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException
from ..models.writing import (
    WritingRequest, PreviewResponse, ExecuteResponse, WritingStatus,
    WritingHistoryItem, HistoryDeleteRequest,
)
from ..core.robot_state import job_state
from ..core import history, tuning_config

# path_generator.py import (같은 저장소). 저장소 루트를 sys.path 에 추가한다.
# 이 파일: server/app/routers/writing.py → parents[3] = 저장소 루트(cobot_writing/)
sys.path.append(str(Path(__file__).resolve().parents[3]))
import cobot_writing.path_generator as pgmod
from cobot_writing.path_generator import PathGenerator

router = APIRouter(prefix="/writing", tags=["글씨 쓰기"])


def _make_generator(req):
    """요청값(폰트·크기·여백·fill) + 관리자 경로 파라미터(줄/글자 간격·도화지·해칭·곡선)로
    PathGenerator 를 만든다. 관리자 값은 tuning_config 에서 읽어 실시간 반영된다."""
    cfg = tuning_config.get_path()
    pgmod._CURVE_STEPS = int(cfg["curve_steps"])   # 모듈 전역(곡선 분해 세밀도) 반영
    return PathGenerator(
        font_name=req.font_name,
        char_height_mm=req.char_height_mm,
        margin_mm=req.margin_mm,
        fill_mode=req.fill_mode,
        line_spacing_factor=cfg["line_spacing_factor"],
        char_spacing_mm=cfg["char_spacing_mm"],
        paper_width_mm=cfg["paper_width_mm"],
        paper_height_mm=cfg["paper_height_mm"],
        hatch_spacing_mm=cfg["hatch_spacing_mm"],
    )


@router.post("/preview", response_model=PreviewResponse, summary="미리보기 경로 생성")
def preview(req: WritingRequest):
    gen = _make_generator(req)
    path = gen.generate(req.text)
    waypoints = [[x, y, int(pd)] for x, y, pd in path]
    return PreviewResponse(
        waypoints=waypoints,
        summary={
            "total_points":  len(path),
            "stroke_count":  sum(1 for i, p in enumerate(path)
                                 if p[2] and (i == 0 or not path[i-1][2])),
            "pen_up_count":  sum(1 for p in path if not p[2]),
            "pen_down_count": sum(1 for p in path if p[2]),
            "x_range": [round(min(p[0] for p in path), 1),
                        round(max(p[0] for p in path), 1)],
            "y_range": [round(min(p[1] for p in path), 1),
                        round(max(p[1] for p in path), 1)],
        },
    )


@router.post("/execute", response_model=ExecuteResponse, summary="로봇 글씨 쓰기 실행")
def execute(req: WritingRequest):
    if job_state.status == "writing":
        raise HTTPException(status_code=409, detail="이미 작업이 진행 중입니다.")

    job_state.job_id = str(uuid.uuid4())[:8]
    job_state.status = "writing"
    job_state.progress_pct = 0
    job_state.current_stroke = 0
    job_state.current_char = ""
    job_state.error_msg = ""
    # 작업 경과 타이머 시작 (finished_at=0 = 진행 중)
    job_state.started_at = time.time()
    job_state.finished_at = 0.0

    # 경로 생성 후 ROS2 토픽 발행
    gen = _make_generator(req)
    path = gen.generate(req.text)
    job_state.total_strokes = sum(
        1 for i, p in enumerate(path) if p[2] and (i == 0 or not path[i-1][2])
    )
    # 획 인덱스 → 글자 매핑 저장 (진행률 수신 시 current_char 역추적용)
    job_state.stroke_chars = gen.stroke_char_map(req.text)

    from ..core.ros_node import get_ros_node
    node = get_ros_node()
    if node is None:
        raise HTTPException(status_code=503, detail="ROS2 노드가 준비되지 않았습니다.")
    # 펜 선택을 먼저 발행하고(웨이포인트 수신=작업 시작이므로 순서 중요) 웨이포인트를 발행한다.
    node.publish_pen(req.pen)
    node.publish_waypoints(path)

    # UI가 즉시 '쓰는 중/취소' 상태로 바뀌도록 진행률 브로드캐스트
    from ..core.robot_state import schedule_broadcast
    schedule_broadcast()

    # 이용 내역 기록 (닉네임·입력값·시각)
    history.add_record({
        "job_id":         job_state.job_id,
        "nickname":       (req.nickname or "").strip() or "익명",
        "text":           req.text,
        "font_name":      req.font_name,
        "char_height_mm": req.char_height_mm,
        "margin_mm":      req.margin_mm,
        "fill_mode":      req.fill_mode,
    })

    return ExecuteResponse(job_id=job_state.job_id, status=job_state.status)


@router.delete("/cancel", summary="작업 취소")
def cancel():
    if job_state.status != "writing":
        raise HTTPException(status_code=400, detail="진행 중인 작업이 없습니다.")
    job_state.status = "cancelled"
    if job_state.started_at > 0 and job_state.finished_at == 0.0:
        job_state.finished_at = time.time()   # 타이머 정지
    from ..core.ros_node import get_ros_node
    node = get_ros_node()
    if node:
        node.publish_emergency_stop(True)
    # UI가 즉시 '취소됨'으로 바뀌도록 진행률 브로드캐스트
    from ..core.robot_state import schedule_broadcast
    schedule_broadcast()
    return {"message": "작업이 취소됐습니다."}


@router.get("/history", response_model=List[WritingHistoryItem], summary="이용 내역 조회")
def get_history(limit: int = 100):
    return history.list_records(limit)


@router.delete("/history", summary="이용 내역 삭제 (선택/전체)")
def delete_history(req: HistoryDeleteRequest):
    removed = history.clear_records() if req.all else history.delete_records(req.ids)
    return {"deleted": removed}


@router.get("/status", response_model=WritingStatus, summary="현재 작업 상태 조회")
def get_status():
    from ..core.robot_state import job_elapsed_sec
    return WritingStatus(
        job_id=job_state.job_id,
        status=job_state.status,
        progress_pct=job_state.progress_pct,
        current_stroke=job_state.current_stroke,
        total_strokes=job_state.total_strokes,
        current_char=job_state.current_char,
        error_msg=job_state.error_msg,
        elapsed_sec=job_elapsed_sec(),
        running=job_state.started_at > 0 and job_state.finished_at == 0.0,
    )

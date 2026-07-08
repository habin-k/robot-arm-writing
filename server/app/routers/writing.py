import sys
import uuid
from fastapi import APIRouter, HTTPException
from ..models.writing import WritingRequest, PreviewResponse, ExecuteResponse, WritingStatus
from ..core.robot_state import job_state

# path_generator.py import (같은 저장소)
sys.path.append("/home/dongmin/ws_cobot_pjt/ws_dsr/src/cobot_writing")
from cobot_writing.path_generator import PathGenerator

router = APIRouter(prefix="/writing", tags=["글씨 쓰기"])


@router.post("/preview", response_model=PreviewResponse, summary="미리보기 경로 생성")
def preview(req: WritingRequest):
    gen = PathGenerator(
        font_name=req.font_name,
        char_height_mm=req.char_height_mm,
        margin_mm=req.margin_mm,
    )
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

    # 경로 생성 후 ROS2 토픽 발행
    gen = PathGenerator(
        font_name=req.font_name,
        char_height_mm=req.char_height_mm,
        margin_mm=req.margin_mm,
    )
    path = gen.generate(req.text)
    job_state.total_strokes = sum(
        1 for i, p in enumerate(path) if p[2] and (i == 0 or not path[i-1][2])
    )

    from ..core.ros_node import get_ros_node
    node = get_ros_node()
    if node is None:
        raise HTTPException(status_code=503, detail="ROS2 노드가 준비되지 않았습니다.")
    node.publish_waypoints(path)

    return ExecuteResponse(job_id=job_state.job_id, status=job_state.status)


@router.delete("/cancel", summary="작업 취소")
def cancel():
    if job_state.status != "writing":
        raise HTTPException(status_code=400, detail="진행 중인 작업이 없습니다.")
    job_state.status = "cancelled"
    from ..core.ros_node import get_ros_node
    node = get_ros_node()
    if node:
        node.publish_emergency_stop(True)
    return {"message": "작업이 취소됐습니다."}


@router.get("/status", response_model=WritingStatus, summary="현재 작업 상태 조회")
def get_status():
    return WritingStatus(
        job_id=job_state.job_id,
        status=job_state.status,
        progress_pct=job_state.progress_pct,
        current_stroke=job_state.current_stroke,
        total_strokes=job_state.total_strokes,
        current_char=job_state.current_char,
        error_msg=job_state.error_msg,
    )

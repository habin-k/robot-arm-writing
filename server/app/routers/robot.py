from fastapi import APIRouter, Depends, HTTPException
from ..models.robot import JogRequest, RobotStatus
from ..core.auth import get_current_admin
from ..core.ros_node import get_ros_node

router = APIRouter(prefix="/robot", tags=["로봇 제어"], dependencies=[Depends(get_current_admin)])


def _node():
    node = get_ros_node()
    if node is None:
        raise HTTPException(status_code=503, detail="ROS2 노드가 준비되지 않았습니다.")
    return node


@router.post("/home", summary="원점 복귀")
def go_home():
    _node().publish_go_home()
    return {"message": "원점 복귀 명령 전송"}


@router.post("/emergency-stop", summary="비상정지")
def emergency_stop():
    _node().publish_emergency_stop(True)
    return {"message": "비상정지 명령 전송"}


@router.post("/error-reset", summary="에러 리셋")
def error_reset():
    _node().publish_error_reset()
    return {"message": "에러 리셋 명령 전송"}


@router.post("/retry", summary="작업 재시도 (수동 복구 후)")
def retry_task():
    # 수동 복구 모드(MANUAL_REQUIRED)에서만 성공. 그 외 상태면 task_manager 가 거절 메시지를 준다.
    success, message = _node().call_retry()
    if not success:
        raise HTTPException(status_code=409, detail=message)
    return {"message": message}


@router.post("/grip", summary="그리퍼 집기")
def grip():
    _node().publish_grip(True)
    return {"message": "그립 명령 전송"}


@router.post("/ungrip", summary="그리퍼 놓기")
def ungrip():
    _node().publish_grip(False)
    return {"message": "언그립 명령 전송"}


@router.post("/jog", summary="수동 조그 (연속)")
def jog(req: JogRequest):
    _node().publish_jog(req.axis, req.direction, req.moving, req.speed)
    if req.moving:
        return {"message": f"{req.axis}축 {'+' if req.direction == 1 else '-'} 이동 시작"}
    return {"message": f"{req.axis}축 정지"}


@router.get("/status", response_model=RobotStatus, summary="로봇 상태 조회")
def get_status():
    # TODO: ROS2 토픽에서 실제 값 읽기
    return RobotStatus(
        mode="autonomous",
        is_running=False,
        tcp_position=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        joint_angles=[0.0, 0.0, 90.0, 0.0, 90.0, 0.0],
        error_code=0,
    )

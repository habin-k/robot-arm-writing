from fastapi import APIRouter, Depends
from ..models.robot import JogRequest, RobotStatus
from ..core.auth import get_current_admin

router = APIRouter(prefix="/robot", tags=["로봇 제어"], dependencies=[Depends(get_current_admin)])


@router.post("/home", summary="원점 복귀")
def go_home():
    # TODO: ROS2 서비스 호출
    return {"message": "원점 복귀 명령 전송"}


@router.post("/emergency-stop", summary="비상정지")
def emergency_stop():
    # TODO: ROS2 서비스 호출
    return {"message": "비상정지 명령 전송"}


@router.post("/error-reset", summary="에러 리셋")
def error_reset():
    # TODO: ROS2 서비스 호출
    return {"message": "에러 리셋 명령 전송"}


@router.post("/jog", summary="수동 조그")
def jog(req: JogRequest):
    # TODO: ROS2 서비스 호출
    return {
        "message": f"{req.axis}축 {'+' if req.direction == 1 else '-'}{req.step_mm}mm 조그 명령 전송"
    }


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

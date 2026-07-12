"""관리자 파라미터 설정 API (HMI '파라미터 설정' 탭).

  GET/POST /tuning/motion : 로봇 모션 파라미터. POST 시 저장 + /robot/tuning 발행(실시간 반영).
  GET/POST /tuning/path   : 경로 생성 파라미터. POST 시 저장(다음 preview/execute 부터 반영).

모두 관리자(JWT) 전용.
"""
from fastapi import APIRouter, Depends
from ..core.auth import get_current_admin
from ..core.ros_node import get_ros_node
from ..core import tuning_config
from ..models.tuning import MotionParams, PathParams

router = APIRouter(prefix="/tuning", tags=["파라미터 설정"],
                   dependencies=[Depends(get_current_admin)])


@router.get("/motion", summary="로봇 모션 파라미터 조회")
def get_motion():
    return tuning_config.get_motion()


@router.post("/motion", summary="로봇 모션 파라미터 저장 + 실시간 반영")
def set_motion(params: MotionParams):
    updated = tuning_config.set_motion(params.model_dump(exclude_unset=True, exclude_none=True))
    node = get_ros_node()
    if node is not None:
        node.publish_tuning(updated)   # latched 발행 → task_manager 즉시 반영
    return {"message": "모션 파라미터 적용됨", "motion": updated}


@router.get("/path", summary="경로 생성 파라미터 조회")
def get_path():
    return tuning_config.get_path()


@router.post("/path", summary="경로 생성 파라미터 저장")
def set_path(params: PathParams):
    updated = tuning_config.set_path(params.model_dump(exclude_unset=True, exclude_none=True))
    return {"message": "경로 파라미터 저장됨", "path": updated}

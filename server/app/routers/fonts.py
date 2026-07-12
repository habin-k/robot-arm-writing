import sys
from pathlib import Path
from fastapi import APIRouter

# 서버를 server/에서 직접 실행해도 ROS 패키지 모듈을 import할 수 있게 한다.
sys.path.append(str(Path(__file__).resolve().parents[3]))
from cobot_writing.path_generator import FONT_PATHS

router = APIRouter(prefix="/fonts", tags=["폰트"])

FONT_NAMES = list(FONT_PATHS.keys())  # HMI와 경로 생성기가 같은 폰트 목록을 사용한다.


@router.get("", summary="사용 가능한 폰트 목록")
def get_fonts():
    return {"fonts": FONT_NAMES}

import sys
from pathlib import Path
from fastapi import APIRouter

# 폰트 목록은 path_generator 의 FONT_PATHS 를 단일 소스로 사용한다.
# (여기서 따로 하드코딩하면 목록이 어긋나 HMI엔 뜨는데 실제론 폴백되는 조용한 버그가 생긴다.)
# 저장소 루트를 sys.path 에 추가: 이 파일 server/app/routers/fonts.py → parents[3] = 저장소 루트.
sys.path.append(str(Path(__file__).resolve().parents[3]))
from cobot_writing.path_generator import FONT_PATHS

router = APIRouter(prefix="/fonts", tags=["폰트"])

FONT_NAMES = list(FONT_PATHS.keys())


@router.get("", summary="사용 가능한 폰트 목록")
def get_fonts():
    return {"fonts": FONT_NAMES}

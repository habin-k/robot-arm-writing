from fastapi import APIRouter

router = APIRouter(prefix="/fonts", tags=["폰트"])

FONT_NAMES = ["regular", "bold", "light", "condensed", "extended", "brother"]


@router.get("", summary="사용 가능한 폰트 목록")
def get_fonts():
    return {"fonts": FONT_NAMES}

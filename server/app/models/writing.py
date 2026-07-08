from pydantic import BaseModel, Field
from typing import List, Tuple, Optional


class WritingRequest(BaseModel):
    text: str = Field(..., example="Hello World")
    font_name: str = Field("regular", example="regular")
    char_height_mm: float = Field(15.0, ge=5.0, le=50.0, example=15.0)
    margin_mm: float = Field(20.0, ge=0.0, le=50.0, example=20.0)
    fill_mode: str = Field("outline", description="outline(윤곽선) 또는 hatch(속 채우기)", example="outline")
    skip_surface_detect: bool = Field(False)


class PreviewResponse(BaseModel):
    waypoints: List[List[float]]   # [[x, y, pen_down(0/1)], ...]
    summary: dict


class ExecuteResponse(BaseModel):
    job_id: str
    status: str


class WritingStatus(BaseModel):
    job_id: Optional[str]
    status: str
    progress_pct: int
    current_stroke: int
    total_strokes: int
    current_char: str
    error_msg: str

from pydantic import BaseModel, Field
from typing import Literal, Optional


class JogRequest(BaseModel):
    axis: Literal["x", "y", "z", "rx", "ry", "rz"] = Field(..., example="z")
    direction: Literal[1, -1] = Field(..., example=-1)
    step_mm: float = Field(5.0, ge=0.1, le=100.0, example=5.0)


class RobotStatus(BaseModel):
    mode: str
    is_running: bool
    tcp_position: Optional[list]   # [x, y, z, rx, ry, rz]
    joint_angles: Optional[list]   # [j1, j2, j3, j4, j5, j6]
    error_code: int

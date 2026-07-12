from pydantic import BaseModel, Field
from typing import Literal, Optional


class JogRequest(BaseModel):
    axis: Literal["x", "y", "z", "rx", "ry", "rz"] = Field(..., example="z")
    direction: Literal[1, -1] = Field(1, example=-1)
    moving: bool = Field(True, description="True=이동 시작, False=정지", example=True)
    speed: float = Field(30.0, ge=1.0, le=100.0, description="조그 속도 (mm/s 또는 deg/s)", example=30.0)


class RobotStatus(BaseModel):
    mode: str
    is_running: bool
    tcp_position: Optional[list]   # [x, y, z, rx, ry, rz]
    joint_angles: Optional[list]   # [j1, j2, j3, j4, j5, j6]
    error_code: int

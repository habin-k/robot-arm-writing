"""관리자 파라미터 설정 스키마 (HMI '파라미터 설정' 탭).

모든 필드 Optional → 부분 업데이트 허용(보낸 키만 반영). 위험한 값(0/음수 속도 등)은
검증기로 걸러 로봇이 이상 명령을 받지 않게 한다.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


def _check_pair(v, name):
    if v is None:
        return v
    if len(v) != 2:
        raise ValueError(f"{name} 은 [일반, 회전] 2개 값이어야 합니다")
    if any((x is None or x <= 0) for x in v):
        raise ValueError(f"{name} 값은 0보다 커야 합니다")
    return [float(v[0]), float(v[1])]


class MotionParams(BaseModel):
    """로봇 모션 파라미터 (→ /robot/tuning 발행 → task_manager 실시간 반영)."""
    write_vel:  Optional[List[float]] = Field(None, description="글씨 속도 [일반, 회전]")
    write_acc:  Optional[List[float]] = Field(None, description="글씨 가속 [일반, 회전]")
    travel_vel: Optional[List[float]] = Field(None, description="공이동 속도 [일반, 회전]")
    travel_acc: Optional[List[float]] = Field(None, description="공이동 가속 [일반, 회전]")
    write_force_z: Optional[float] = Field(None, ge=-20.0, le=0.0,
                                           description="붓 누르는 힘 (N, 음수=아래)")
    force_on_z:    Optional[float] = Field(None, ge=0.0, le=300.0,
                                           description="힘제어 켜는 하강 목표 높이 (mm)")
    contact_force: Optional[Dict[str, float]] = Field(None, description="펜별 접촉 판단 힘 (N)")

    @field_validator('write_vel', 'write_acc', 'travel_vel', 'travel_acc')
    @classmethod
    def _pair(cls, v, info):
        return _check_pair(v, info.field_name)

    @field_validator('contact_force')
    @classmethod
    def _cf(cls, v):
        if v is None:
            return v
        for pen, val in v.items():
            if pen not in ('red', 'purple', 'cyan'):
                raise ValueError(f"알 수 없는 펜: {pen}")
            if not (0.1 <= val <= 20.0):
                raise ValueError(f"접촉힘({pen})은 0.1~20 N 범위여야 합니다")
        return v


class PathParams(BaseModel):
    """경로 생성 파라미터 (→ 서버 PathGenerator 에 주입)."""
    line_spacing_factor: Optional[float] = Field(None, ge=0.5, le=5.0)
    char_spacing_mm:     Optional[float] = Field(None, ge=0.0, le=100.0)
    paper_width_mm:      Optional[float] = Field(None, ge=50.0, le=1000.0)
    paper_height_mm:     Optional[float] = Field(None, ge=50.0, le=1000.0)
    hatch_spacing_mm:    Optional[float] = Field(None, ge=0.2, le=10.0)
    curve_steps:         Optional[int]   = Field(None, ge=2, le=60)

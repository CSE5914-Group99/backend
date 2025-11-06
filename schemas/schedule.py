from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScheduleActivity(BaseModel):
    description: str
    timesDays: Optional[str] = None


class ScheduleCourseDetail(BaseModel):
    courseId: str
    sectionId: Optional[str] = None
    timesDays: Optional[str] = None


class SchedulePayload(BaseModel):
    scheduleId: Optional[int] = None
    name: Optional[str] = "Untitled"
    items: Optional[List[ScheduleCourseDetail]] = None
    favorite: Optional[bool] = None
    difficultyScore: Optional[float] = None
    activities: Optional[List[ScheduleActivity]] = None


class ScheduleSaved(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduleId: int
    userId: int
    name: str
    items: List[ScheduleCourseDetail]
    favorite: bool
    difficultyScore: float
    activities: List[ScheduleActivity]


class ScheduleLoadRequest(BaseModel):
    courseIds: List[str]
    constraints: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"maxCredits": 18, "noFri": False}
    )


class ScheduleLoadResult(BaseModel):
    weeklyHours: float
    byCourse: Dict[str, float]

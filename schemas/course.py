from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CourseRating(BaseModel):
    courseId: str
    overall: float = Field(ge=0, le=5)
    difficulty: float = Field(ge=0, le=5)
    workload_hours_per_week: float = Field(ge=0)


class CompareItem(BaseModel):
    courseId: str
    term: Optional[str] = None


class CoursesCompareRequest(BaseModel):
    courses: List[CompareItem]
    weights: Optional[Dict[str, float]] = Field(
        default_factory=lambda: {"difficulty": 0.5, "workload": 0.5}
    )


class CoursesCompareResult(BaseModel):
    rankedCourses: List[str]
    scores: Dict[str, float]

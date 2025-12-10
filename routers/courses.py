from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from agents.class_grading_agent import ClassScore
from agents.schedule_grading_agent import ClassTeacherTuple, ScheduleScore
from agents.class_recommender_agent import (
    ScheduleClassWithTime,
    ModificationRequest,
    RecommenderOutput,
)
from db.session import get_session
from services import course_service

courses_router = APIRouter(prefix="/courses", tags=["courses"])

@courses_router.get("/ratings/{courseId}", response_model=ClassScore)
async def ratings_courseId(
    courseId: str,
    teacher_name: str | None = None,
    session: AsyncSession = Depends(get_session)
):
    # 1. Without teacher name: /courses/ratings/CSE2331
    # 2. With teacher name: /courses/ratings/CSE2331?teacher_name=John%20Doe
    return await course_service.get_course_rating(courseId, teacher_name, session)

# Request model for schedule-load endpoint
class ScheduleLoadRequest(BaseModel):
    courses: List[ClassTeacherTuple]
    constraints: str | None = None

@courses_router.post("/schedule-load", response_model=ScheduleScore)
async def schedule_load(
    request: ScheduleLoadRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Score a complete schedule of classes.
    Takes a list of class/teacher tuples and returns a comprehensive schedule analysis
    including individual class scores and overall schedule difficulty metrics.
    """
    return await course_service.grade_schedule(request.courses, request.constraints, session)


class ClassRecommendationRequest(BaseModel):
    schedule: List[ScheduleClassWithTime]
    schedule_score: ScheduleScore
    modification_requests: List[ModificationRequest]

@courses_router.post("/class-recommendations", response_model=RecommenderOutput)
async def class_recommendations(
    request: ClassRecommendationRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Get class recommendations for modifying a schedule.

    This endpoint helps students find alternative classes for their schedule.
    It searches for options, filters out time conflicts, grades each alternative,
    and returns 2-4 schedule modification options.

    Request body structure:
    {
      "schedule": [
        {
          "class_id": "CSE 2331",
          "teacher": "Smith",  // Optional: can be null
          "time_slots": [
            {
              "start_time": "10:00",  // HH:mm format
              "end_time": "10:55",
              "repeat_days": ["Monday", "Wednesday", "Friday"]
            }
          ]
        }
      ],
      "schedule_score": {
        "class_scores": [
          {
            "class_id": "cse2331",  // Normalized: lowercase, no spaces
            "teacher": "smith",  // Normalized: lowercase, no spaces, or "unknown"
            "score": 75,  // 1-100
            "ch": 3,
            "summary": "Challenging data structures course",
            "time_load": 6.5,  // 0-8 hours/week
            "rigor": 70,  // 0-100
            "assessment_intensity": 65,  // 0-100
            "project_intensity": 80,  // 0-100
            "pace": 70,  // 0-100
            "pre_reqs": ["CSE 2221"],
            "co_reqs": [],
            "tags": ["programming", "data-structures"],
            "evidence_snippets": ["Student review quotes..."],
            "confidence": 0.85  // 0.0-1.0
          },
          {
            "class_id": "math2568",
            "teacher": "unknown",
            "score": 60,
            "ch": 3,
            "summary": "Linear algebra course",
            "time_load": 5.0,
            "rigor": 65,
            "assessment_intensity": 60,
            "project_intensity": 30,
            "pace": 55,
            "pre_reqs": ["MATH 1151"],
            "co_reqs": [],
            "tags": ["math", "theory"],
            "evidence_snippets": ["Conceptually challenging"],
            "confidence": 0.75
          }
        ],
        "total_credit_hours": 6,
        "num_classes": 2,
        "summary": "Moderately challenging schedule",
        "adjusted_difficulty": 68,  // 1-100
        "adjusted_assessment_intensity": 62,  // 0-100
        "adjusted_project_intensity": 55,  // 0-100
        "time_load": 11.5,  // 0-30 hours/week for entire schedule
        "adjusted_rigor": 67,  // 0-100
        "constraints": "Working 15 hours per week",
        "confidence": 0.8  // 0.0-1.0
      },
      "modification_requests": [
        {
          "class_to_replace": "CSE 2331",  // Optional: null if adding a new class
          "reason": "Too difficult for my current workload",
          "criteria": "Easier CSE class, morning times preferred"
        }
      ]
    }

    Time format:
    - start_time/end_time: HH:mm format (e.g., "10:00", "14:30")
    - repeat_days: List of day names (e.g., ["Monday", "Wednesday", "Friday"])

    Response:
    {
      "alterations": [
        {
          "alteration_name": "Easiest Option",
          "description": "Replaces CSE 2331 with easier alternative",
          "classes_to_remove": ["CSE 2331"],
          "classes_to_add": [
            {
              "class_id": "CSE 2221",
              "teacher": "Jones",
              "time_slots": [...],
              "class_score": {
                "score": 45,
                "ch": 4,
                "summary": "Intro to software development...",
                "time_load": 6.5,
                "rigor": 40,
                "assessment_intensity": 50,
                "project_intensity": 60,
                "pace": 45,
                "pre_reqs": ["CSE 1223"],
                "co_reqs": [],
                "tags": ["programming", "java"],
                "evidence_snippets": ["Student review..."],
                "confidence": 0.8
              },
              "why_recommended": "Significantly easier, same major requirement"
            }
          ],
          "estimated_difficulty_change": -23,
          "estimated_time_change": -2.5,
          "confidence": 0.8,
          "warnings": ["Prerequisite: CSE 1223"]
        }
      ],
      "overall_summary": "Found 3 good alternatives...",
      "confidence": 0.75
    }

    Workflow:
    1. Searches OSU courses, RateMyProfessor, and web for alternatives
    2. Filters out classes that conflict with your remaining schedule
    3. Grades each alternative using the class grading agent (parallel)
    4. Generates 2-4 alteration options (easiest, best-rated, etc.)

    Note: This endpoint can take 30-60 seconds due to multiple API calls.
    """
    return await course_service.get_class_recommendations(
        request.schedule,
        request.schedule_score,
        request.modification_requests,
        session
    )

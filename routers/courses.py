from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Body
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from agents.class_grading_agent import ClassScore, class_grading_graph
from agents.schedule_grading_agent import ClassTeacherTuple, ScheduleScore, schedule_grading_graph
from agents.class_recommender_agent import (
    ScheduleClassWithTime,
    ModificationRequest,
    RecommenderOutput,
    TimeSlot,
    class_recommender_graph
)
from db.session import get_session

courses_router = APIRouter(prefix="/courses", tags=["courses"])

@courses_router.get("/ratings/{courseId}", response_model=ClassScore)
async def ratings_courseId(
    courseId: str,
    teacher_name: str | None = None,
    session: AsyncSession = Depends(get_session)
):
    # 1. Without teacher name: /courses/ratings/CSE2331
    # 2. With teacher name: /courses/ratings/CSE2331?teacher_name=John%20Doe
    courseId = courseId.replace(" ", "").lower()
    teacher_name_id_form = teacher_name.replace(" ", "").lower() if teacher_name else 'unknown'

    # Include teacher name in the message if provided
    if teacher_name and teacher_name != 'unknown':
        message_content = f"Evaluate the class {courseId} taught by Professor {teacher_name}"
    else:
        message_content = f"Evaluate the class {courseId} (no specific instructor provided)"

    test_messages = [HumanMessage(content=message_content)]
    initial_state = {
        "messages": test_messages,
        "class_name": courseId,
        "teacher_name": teacher_name_id_form,
        "class_score": None,
        "cached": False,
        "session": session,  # Pass session for database caching
    }
    result = await class_grading_graph.ainvoke(initial_state)
    return result["class_score"]

# Request model for schedule-load endpoint
class ScheduleLoadRequest(BaseModel):
    courses: List[ClassTeacherTuple]
    user_id: int
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

    The scored schedule will be saved to the database and associated with the user.
    """
    initial_state = {
        "schedule": request.courses,
        "schedule_score": None,
        "messages": [],
        "user_id": request.user_id,
        "constraints": request.constraints,
        "schedule_id": None,
        "session": session
    }

    # Run the schedule grading graph
    result = await schedule_grading_graph.ainvoke(initial_state)

    # Return the complete schedule score object
    return result["schedule_score"]


@courses_router.post("/compare", response_model=List[ClassScore])
async def compare(courseIds: List[str]):
    return

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

    Request body:
    {
      "schedule": [
        {
          "class_id": "CSE 2331",
          "teacher": "Smith",
          "time_slots": [
            {"day": "M", "start_time": 600, "end_time": 655},
            {"day": "W", "start_time": 600, "end_time": 655},
            {"day": "F", "start_time": 600, "end_time": 655}
          ]
        }
      ],
      "schedule_score": { ... },
      "modification_requests": [
        {
          "class_to_replace": "CSE 2331",
          "reason": "Too difficult",
          "criteria": "Easier CSE class, morning times"
        }
      ]
    }

    Time format:
    - day: "M" (Mon), "T" (Tue), "W" (Wed), "R" (Thu), "F" (Fri), "S" (Sat), "U" (Sun)
    - start_time/end_time: Minutes from midnight
      - 8:00 AM  = 480
      - 10:00 AM = 600
      - 1:30 PM  = 810
      - 3:00 PM  = 900

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
    initial_state = {
        "messages": [],
        "schedule": request.schedule,
        "schedule_score": request.schedule_score,
        "modification_requests": request.modification_requests,
        "alternatives_found": None,
        "feasible_alternatives": None,
        "graded_alternatives": {},
        "recommender_output": None,
        "session": session
    }

    # Run the class recommender graph
    result = await class_recommender_graph.ainvoke(initial_state)

    return result["recommender_output"]

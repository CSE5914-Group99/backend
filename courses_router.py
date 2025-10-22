from fastapi import APIRouter
from typing import List
from agents.class_grading_agent import ClassScore, class_grading_graph
from langchain_core.messages import HumanMessage

# User microservice router
courses_router = APIRouter(prefix="/courses", tags=["courses"])

@courses_router.get("/ratings/{courseId}", response_model=ClassScore)
async def ratings_courseId(courseId: str):
    test_messages = [HumanMessage(content=f"Evaluate the class {courseId}")]
    initial_state = {
        "messages": test_messages,
        "class_name": courseId,
        "class_score": None,
        "cached": False
    }
    result = class_grading_graph.invoke(initial_state)
    return result["class_score"]

@courses_router.post("/schedule-load", response_model=List[ClassScore])
async def compare(courseIds: List[str]):
    return

@courses_router.post("/compare", response_model=List[ClassScore])
async def compare(courseIds: List[str]):
    return

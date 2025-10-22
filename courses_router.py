from fastapi import APIRouter
from typing import List
from agents.class_grading_agent import ClassScore, class_grading_graph
from langchain_core.messages import HumanMessage

# User microservice router
courses_router = APIRouter(prefix="/courses", tags=["courses"])

@courses_router.get("/ratings/{courseId}", response_model=ClassScore)
async def ratings_courseId(courseId: str):
    # Return hardcoded data for CSE2331
    if courseId == "CSE2331":
        return ClassScore(
            score=73,
            ch=3,
            summary="A mid-level, conceptually rigorous data-structures and algorithms course (proofs, complexity, NP-completeness) that is challenging and time-consuming but essential for CS/CSE majors.",
            time_load=6.0,
            rigor=75,
            assessment_intensity=65,
            project_intensity=65,
            pace=70,
            pre_reqs=[
                "CSE 2231",
                "CSE 2321",
                "STAT 3460 or STAT 3470"
            ],
            co_reqs=[
                "Math 3345 (concurrent in some offerings)"
            ],
            tags=[
                "algorithms",
                "data-structures",
                "proofs",
                "NP-completeness",
                "randomized-algorithms",
                "hashing",
                "graphs",
                "time-consuming",
                "core-course"
            ],
            evidence_snippets=[
                '''"Design/analysis of algorithms and data structures; divide-and-conquer; sorting and selection, search trees, hashing, graph algorithms, string matching; probabilistic analysis; randomized algorithms; NP-completeness." — OSU course listing/syllabus''',
                '''"Be competent with using asymptotic notation ... Be familiar with designing graph algorithms ... Be familiar with the use of balanced trees ... Be familiar with hashing." — OSU syllabus objectives''',
                '''"Prereq: 2231, 2321, and Stat 3460 or 3470 ... Concur: Math 3345." — OSU course catalog entry''',
                '''Student discussion note: "CSE 2331 & 2421 Study Resource ... Nick Painter's playlist is also great for studying Foundation II." — student forum (Reddit)'''
            ],
            confidence=0.75
        )

    # For other courses, use the agent
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

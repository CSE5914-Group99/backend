from fastapi import APIRouter, BackgroundTasks, Query
from typing import Optional, Dict
import time
from agents.class_grading_agent import ClassScore, class_grading_graph
from langchain_core.messages import HumanMessage
from models import CourseRating, CoursesCompareRequest, CoursesCompareResult, ScheduleLoadRequest, ScheduleLoadResult
from agents.class_grading_agent import ClassScore

courses_router = APIRouter(prefix="/courses", tags=["courses"])

def classscore_to_courserating(course_id: str, cs: ClassScore) -> CourseRating:
    """
    Map ClassScore (0-100-ish scales + hours) to your 0-5 scales.
    Adjust the mapping to your liking.
    """
    overall = max(0.0, min(5.0, round(cs.score / 20.0, 1)))          # 0..100 -> 0..5
    difficulty = max(0.0, min(5.0, round(cs.rigor / 20.0, 1)))       # 0..100 -> 0..5
    workload = float(cs.time_load) if cs.time_load is not None else 6.0
    return CourseRating(courseId=course_id, overall=overall, difficulty=difficulty, workload_hours_per_week=workload)


# --- trivial in-memory cache ---
_CACHE: Dict[str, Dict] = {}  # key -> {"value": CourseRating, "ts": float}
TTL_SECONDS = 6 * 60 * 60     # 6 hours

def get_cached(course_id: str) -> Optional[CourseRating]:
    rec = _CACHE.get(course_id.upper())
    if not rec:
        return None
    if time.time() - rec["ts"] > TTL_SECONDS:
        return None
    return rec["value"]

def put_cache(cr: CourseRating):
    _CACHE[cr.courseId.upper()] = {"value": cr, "ts": time.time()}

def fetch_with_agent(course_id: str) -> CourseRating:
    """Blocking call to the agent, then adapt."""
    init = {
        "messages": [HumanMessage(content=f"Evaluate the class {course_id}")],
        "class_name": course_id,
        "class_score": None,
        "cached": False,
    }
    result = class_grading_graph.invoke(init)
    cs: ClassScore = result["class_score"]
    return classscore_to_courserating(course_id, cs)

def refresh_cache_bg(course_id: str):
    cr = fetch_with_agent(course_id)
    put_cache(cr)

@courses_router.get("/ratings/{courseId}", response_model=CourseRating, summary="Get recent ratings for a course")
async def ratings_courseId(
    courseId: str,
    background: BackgroundTasks,
    fresh: bool = Query(False, description="Force refresh from source (may be slow)")
):
    # 1) Fast hard-coded path for CSE2331
    if courseId.upper() == "CSE2331":
        cr = CourseRating(courseId="CSE2331", overall=3.7, difficulty=3.8, workload_hours_per_week=6.0)
        # keep a cached copy too
        put_cache(cr)
        return cr

    # 2) If not forcing fresh, try cache first
    if not fresh:
        cached = get_cached(courseId)
        if cached:
            # kick off a background refresh to keep it fresh (stale-while-revalidate)
            background.add_task(refresh_cache_bg, courseId)
            return cached

    # 3) Either fresh=True or cache miss → do the real fetch (may be slow)
    cr = fetch_with_agent(courseId)
    put_cache(cr)
    return cr

@courses_router.post(
    "/compare",
    response_model=CoursesCompareResult,
    summary="Compare multiple courses on difficulty & workload",
)
async def compare_courses(body: CoursesCompareRequest):
    # TODO: compute composite scores
    scores = {c.courseId: 0.7 for c in body.courses}
    ranked = sorted(scores.keys(), key=scores.get, reverse=True)
    return CoursesCompareResult(rankedCourses=ranked, scores=scores)

@courses_router.post(
    "/schedule-load",
    response_model=ScheduleLoadResult,
    summary="Simulate overall weekly load using ratings (+ constraints)",
)
async def simulate_schedule_load(body: ScheduleLoadRequest):
    # TODO: real simulation logic
    per_course = {cid: 6.0 for cid in body.courseIds}
    return ScheduleLoadResult(weeklyHours=sum(per_course.values()), byCourse=per_course)

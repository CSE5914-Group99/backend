from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from services.schedule_generator import generate_schedules, TimeSlot, ParsedSection
from agents.schedule_grading_agent import schedule_grading_graph, ClassTeacherTuple, ScheduleScore
from schemas.schedule import Schedule, Course, Event
# from db.session import get_session # Not used directly here

router = APIRouter(
    prefix="/generate-schedule",
    tags=["generate-schedule"],
)

class GenerateScheduleRequest(BaseModel):
    courses: List[Course]
    term: str = "Autumn 2024"
    campus: str = "Columbus"
    events: List[Event] = []
    preferences: Optional[dict] = None

class GenerateScheduleResponse(BaseModel):
    schedules: List[Schedule]

@router.post("/", response_model=GenerateScheduleResponse)
async def generate_schedule_endpoint(request: GenerateScheduleRequest):
    # 1. Convert events to TimeSlots for generator
    generator_events = []
    for event in request.events:
        # Parse event times
        # Event schema has startTime/endTime as HH:mm string
        # And repeatDays as list of strings
        
        # Helper to parse HH:mm
        def parse_hm(t):
            h, m = map(int, t.split(':'))
            return h * 60 + m
            
        start_min = parse_hm(event.startTime)
        end_min = parse_hm(event.endTime)
        
        for day in event.repeatDays:
            generator_events.append(TimeSlot(
                day=day,
                start_minutes=start_min,
                end_minutes=end_min
            ))

    # 2. Generate schedules
    # We limit to 3 candidates for grading to save time/tokens
    candidates, missing_courses = await generate_schedules(
        request.courses,
        request.term,
        request.campus,
        events=generator_events,
        max_schedules=3
    )
    
    if not candidates and missing_courses:
        # If no valid schedules found but we have missing courses, 
        # create a dummy empty schedule so we can return the missing ones.
        candidates = [[]]
    
    if not candidates and not missing_courses:
        # If no candidates and no missing courses (meaning conflict or empty request), return empty.
        return GenerateScheduleResponse(schedules=[])

    # 3. Convert candidates to Schedule objects (without grading)
    schedules = []
    
    for index, candidate in enumerate(candidates):
        courses_for_schema = []
        
        for section in candidate:
            # Create Course schema object
            # We need to map ParsedSection to Course
            
            # Find first slot to get start/end time (assuming consistent)
            s_time = None
            e_time = None
            days = []
            if section.time_slots:
                # Format back to HH:mm
                def fmt_hm(m):
                    h = m // 60
                    mn = m % 60
                    return f"{h:02d}:{mn:02d}"
                
                s_time = fmt_hm(section.time_slots[0].start_minutes)
                e_time = fmt_hm(section.time_slots[0].end_minutes)
                days = list(set(s.day for s in section.time_slots))
            
            # Determine mode
            mode = section.section_data.mode
            
            # Determine type (Lecture/Lab/Recitation)
            course_type = section.section_data.type

            course_obj = Course(
                courseId=f"{section.course_subject} {section.course_number}",
                title=section.section_data.title,
                instructor=section.section_data.instructor,
                startTime=s_time,
                endTime=e_time,
                repeatDays=days,
                campus=request.campus,
                semester=request.term,
                session=section.section_data.session,
                mode=mode,
                type=course_type,
                status=section.section_data.status
            )
            courses_for_schema.append(course_obj)
            
        # Add missing courses to the schedule with empty details
        for m_course in missing_courses:
            courses_for_schema.append(Course(
                courseId=m_course,
                campus=request.campus,
                semester=request.term,
                # Other fields will be None/null, indicating missing info
            ))
        
        # Create Schedule schema object with default scores
        sched = Schedule(
            id=index, # Temporary ID
            name=f"Option {index + 1}",
            favorite=False,
            campus=request.campus,
            semester=request.term,
            courses=courses_for_schema,
            events=request.events,
            difficultyScore=0,
            weeklyHours=0,
            creditHours=0,
        )
        schedules.append(sched)

    return GenerateScheduleResponse(schedules=schedules)


class AnalyzeSchedulesRequest(BaseModel):
    schedules: List[Schedule]
    preferences: Optional[dict] = None

@router.post("/analyze", response_model=List[Schedule])
async def analyze_schedules_endpoint(request: AnalyzeSchedulesRequest):
    """
    Analyze a list of schedules using the AI agent to calculate difficulty, time load, etc.
    """
    async def analyze_one(schedule: Schedule):
        # Convert Schedule to ClassTeacherTuple for agent
        schedule_tuples = []
        for course in schedule.courses:
            # We assume courseId is like "CSE 2231"
            schedule_tuples.append(ClassTeacherTuple(
                class_id=course.courseId,
                teacher=course.instructor
            ))
            
        # Run agent
        initial_state = {
            "schedule": schedule_tuples,
            "schedule_score": None,
            "messages": [],
            "constraints": str(request.preferences) if request.preferences else None,
            "session": None 
        }
        
        try:
            print(f"Starting analysis for schedule {schedule.id} with {len(schedule_tuples)} courses")
            result = await schedule_grading_graph.ainvoke(initial_state)
            score: ScheduleScore = result.get("schedule_score")
            
            if score:
                print(f"Analysis complete for schedule {schedule.id}. Score: {score.adjusted_difficulty}")
                schedule.difficultyScore = score.adjusted_difficulty
                schedule.weeklyHours = score.time_load
                schedule.creditHours = score.total_credit_hours
                
                # Update individual course scores
                if score.class_scores:
                    print(f"Updating {len(score.class_scores)} course scores for schedule {schedule.id}")
                    for course in schedule.courses:
                        # Normalize course info to match agent's keys
                        c_id = course.courseId.replace(" ", "").lower() if course.courseId else ""
                        t_name = course.instructor.replace(" ", "").lower() if course.instructor else "unknown"
                        
                        # Find matching score
                        found = False
                        for key, class_score in score.class_scores.items():
                            # print(f"Comparing {c_id}|{t_name} with {key.class_id}|{key.teacher}")
                            if key.class_id == c_id and key.teacher == t_name:
                                course.difficultyRating = class_score.score
                                found = True
                                break
                        if not found:
                            print(f"No score found for {c_id} {t_name}")
                else:
                    print(f"No class scores returned for schedule {schedule.id}")
            else:
                print(f"No score object returned for schedule {schedule.id}")
        except Exception as e:
            print(f"Error analyzing schedule {schedule.id}: {e}")
            import traceback
            traceback.print_exc()
            
        return schedule

    # Run analyses sequentially to avoid rate limits and timeouts
    analyzed_schedules = []
    for s in request.schedules:
        analyzed = await analyze_one(s)
        analyzed_schedules.append(analyzed)
    
    return analyzed_schedules

import asyncio
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel

from services.osu_course_search import fetch_osu_course_sections, CourseSection

from agents.class_grading_agent import class_grading_graph
from agents.schedule_grading_agent import create_class_key
from langchain_core.messages import HumanMessage
from db.session import get_session_factory

LOGGER = logging.getLogger(__name__)

class TimeSlot(BaseModel):
    day: str
    start_minutes: int
    end_minutes: int

    def overlaps(self, other: 'TimeSlot') -> bool:
        if self.day != other.day:
            return False
        return max(self.start_minutes, other.start_minutes) < min(self.end_minutes, other.end_minutes)

class ParsedSection(BaseModel):
    course_subject: str
    course_number: str
    section_data: CourseSection
    time_slots: List[TimeSlot]

    @property
    def full_course_id(self) -> str:
        return f"{self.course_subject} {self.course_number}"

def parse_time_str(time_str: str) -> int:
    """Convert HH:MM (24h or 12h) to minutes from midnight."""
    # This is a simplified parser. OSU times are usually like "10:00" or "1:00PM"
    # But the scraper returns "10:00 - 11:15". It doesn't explicitly say AM/PM sometimes?
    # Let's assume 24h if possible, or handle AM/PM if present.
    # Actually, looking at scraper output "MoWe 10:00 - 11:15", it seems to be 24h or ambiguous.
    # Let's assume standard university times. 8:00 is AM, 11:00 is AM, 12:00 is PM, 1:00 is 13:00.
    # Wait, if it says "1:00", is it 1 AM or 1 PM? Usually 1 PM.
    # Let's try to parse with datetime.
    
    # If AM/PM is missing, we might need heuristics.
    # Classes usually between 8:00 and 22:00.
    # If < 8:00, add 12 hours (unless it's like 7:30 AM).
    # But "10:00" is 10 AM. "1:00" is 1 PM.
    
    try:
        dt = datetime.strptime(time_str, "%I:%M%p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        pass

    try:
        # Try 24h
        dt = datetime.strptime(time_str, "%H:%M")
        # Heuristic: if < 7:00, add 12 hours (assuming PM)
        # e.g. 1:00 -> 13:00. 6:00 -> 18:00.
        # But 8:00 -> 8:00.
        minutes = dt.hour * 60 + dt.minute
        if dt.hour < 7: 
            minutes += 12 * 60
        return minutes
    except ValueError:
        return 0

def parse_days_times(days_times: str) -> List[TimeSlot]:
    """Parse 'MoWe 10:00 - 11:15' into TimeSlots."""
    if not days_times or days_times == "TBA":
        return []
    
    # Split days and times
    # Regex to find the time part
    match = re.search(r'(\d{1,2}:\d{2}(?:[AP]M)?)\s*-\s*(\d{1,2}:\d{2}(?:[AP]M)?)', days_times)
    if not match:
        return []
    
    start_str = match.group(1)
    end_str = match.group(2)
    
    start_minutes = parse_time_str(start_str)
    end_minutes = parse_time_str(end_str)
    
    # Adjust end time if it appears to be before start time (e.g. crossing noon without PM marker)
    if end_minutes < start_minutes:
        end_minutes += 12 * 60

    # Extract days
    days_part = days_times[:match.start()].strip()
    # OSU days: Mo, Tu, We, Th, Fr, Sa, Su
    # Sometimes "MoWeFr"
    
    days_map = {
        "Mo": "Monday",
        "Tu": "Tuesday",
        "We": "Wednesday",
        "Th": "Thursday",
        "Fr": "Friday",
        "Sa": "Saturday",
        "Su": "Sunday"
    }
    
    slots = []
    i = 0
    while i < len(days_part):
        chunk = days_part[i:i+2]
        if chunk in days_map:
            slots.append(TimeSlot(day=days_map[chunk], start_minutes=start_minutes, end_minutes=end_minutes))
            i += 2
        else:
            i += 1
            
    return slots

from schemas.schedule import (
    Course, Schedule, Event, 
    GenerateScheduleRequest, GenerateScheduleResponse, AnalyzeSchedulesRequest
)
from agents.schedule_grading_agent import schedule_grading_graph, ClassTeacherTuple, ScheduleScore

async def generate_schedules(
    courses: List[Course],
    term: str,
    campus: str,
    events: List[TimeSlot] = [],
    max_schedules: int = 5
) -> Tuple[List[List[ParsedSection]], List[str]]:
    """
    Generate valid schedules for the given courses.
    Handles both fixed (pre-selected) courses and variable courses.
    Returns a tuple: (valid_schedules, missing_courses)
    """
    LOGGER.info(f"Generating schedules for {len(courses)} courses. Term: {term}, Campus: {campus}")
    
    fixed_sections: List[ParsedSection] = []
    variable_courses: List[str] = []
    
    # 1. Separate fixed and variable courses
    for course in courses:
        # Check if course is "locked" (has specific time/section info)
        # We assume if startTime and endTime are present, it's a specific section
        if course.startTime and course.endTime and course.repeatDays:
            # Create a ParsedSection for this fixed course
            # We need to convert Course schema back to ParsedSection
            # Note: CourseSection data might be incomplete (e.g. room, instructor) if not provided
            # but we mainly need time_slots for conflict checking.
            
            # Parse times
            def parse_hm(t):
                try:
                    h, m = map(int, t.split(':'))
                    return h * 60 + m
                except:
                    return 0
            
            start_min = parse_hm(course.startTime)
            end_min = parse_hm(course.endTime)
            
            slots = []
            for day in course.repeatDays:
                slots.append(TimeSlot(
                    day=day,
                    start_minutes=start_min,
                    end_minutes=end_min
                ))
            
            # Extract subject/number from courseId
            parts = course.courseId.split()
            subj = parts[0] if len(parts) > 0 else "Unknown"
            num = parts[1] if len(parts) > 1 else "000"
            
            fixed_sections.append(ParsedSection(
                course_subject=subj,
                course_number=num,
                section_data=CourseSection(
                    title=course.title,
                    instructor=course.instructor,
                    startTime=course.startTime,
                    endTime=course.endTime,
                    repeatDays=course.repeatDays,
                    session=course.session,
                    campus=campus,
                    semester=term
                ),
                time_slots=slots
            ))
        else:
            variable_courses.append(course.courseId)

    LOGGER.info(f"Fixed sections: {len(fixed_sections)}, Variable courses: {variable_courses}")

    missing_courses: List[str] = []
    # 2. Fetch sections for variable courses
    tasks = []
    task_course_codes = []
    for code in variable_courses:
        # Try to parse subject and number using regex to handle "CSE2331" and "CSE 2331"
        match = re.match(r"([A-Za-z]+)\s*(\d+)", code)
        if match:
            subject = match.group(1).upper()
            number = match.group(2)
            tasks.append(fetch_osu_course_sections(subject, number, term=term, campus=campus))
            task_course_codes.append(code)
        else:
            # Fallback to split if regex fails (though regex covers most cases)
            parts = code.split()
            if len(parts) >= 2:
                subject = parts[0].upper()
                number = parts[1]
                tasks.append(fetch_osu_course_sections(subject, number, term=term, campus=campus))
                task_course_codes.append(code)
            else:
                LOGGER.warning(f"Invalid course code format: {code}")
                missing_courses.append(code)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    course_sections_map: Dict[str, List[ParsedSection]] = {}
    
    for i, res in enumerate(results):
        code = task_course_codes[i]
        if isinstance(res, Exception):
            LOGGER.error(f"Error fetching {code}: {res}")
            missing_courses.append(code)
            continue
            
        # Parse sections
        parsed_sections = []
        for sec in res.sections:
            # Filter out sections with TBD/TBA times or missing times
            if not sec.startTime or not sec.endTime:
                continue
                
            s_time = sec.startTime.upper()
            e_time = sec.endTime.upper()
            
            if "TBD" in s_time or "TBA" in s_time or "ARRANGED" in s_time:
                continue
            if "TBD" in e_time or "TBA" in e_time or "ARRANGED" in e_time:
                continue

            # Parse times
            # New CourseSection already has parsed times
            slots = []
            if sec.startTime and sec.endTime and sec.repeatDays:
                start_min = parse_time_str(sec.startTime)
                end_min = parse_time_str(sec.endTime)
                for day in sec.repeatDays:
                    slots.append(TimeSlot(
                        day=day,
                        start_minutes=start_min,
                        end_minutes=end_min
                    ))
            
            # If no valid slots were parsed (e.g. no days listed), skip this section
            if not slots:
                continue
            
            parsed_sections.append(ParsedSection(
                course_subject=res.subject,
                course_number=res.course_number,
                section_data=sec,
                time_slots=slots
            ))
        
        if parsed_sections:
            LOGGER.info(f"Found {len(parsed_sections)} sections for {code}")
            course_sections_map[code] = parsed_sections
        else:
            LOGGER.warning(f"No sections found for {code}")
            missing_courses.append(code)
            
    # 3. Generate combinations (Backtracking)
    valid_schedules: List[List[ParsedSection]] = []
    
    # Sort courses by number of sections (heuristic: most constrained first)
    sorted_courses = sorted(course_sections_map.keys(), key=lambda k: len(course_sections_map[k]))
    
    def backtrack(course_idx: int, current_schedule: List[ParsedSection]):
        if len(valid_schedules) >= max_schedules:
            return

        if course_idx == len(sorted_courses):
            # Combine fixed sections with the generated variable sections
            full_schedule = fixed_sections + list(current_schedule)
            valid_schedules.append(full_schedule)
            return

        course_code = sorted_courses[course_idx]
        sections = course_sections_map[course_code]
        
        for section in sections:
            # Check conflicts
            conflict = False
            
            # Check against current variable schedule
            for existing in current_schedule:
                for s1 in section.time_slots:
                    for s2 in existing.time_slots:
                        if s1.overlaps(s2):
                            conflict = True
                            break
                    if conflict: break
                if conflict: break
            
            if conflict: continue

            # Check against fixed sections
            for fixed in fixed_sections:
                for s1 in section.time_slots:
                    for s2 in fixed.time_slots:
                        if s1.overlaps(s2):
                            conflict = True
                            break
                    if conflict: break
                if conflict: break
            
            if conflict: continue
            
            # Check against events
            for event in events:
                for s1 in section.time_slots:
                    if s1.overlaps(event):
                        conflict = True
                        break
                if conflict: break
                
            if conflict: continue
            
            # Add and recurse
            current_schedule.append(section)
            backtrack(course_idx + 1, current_schedule)
            current_schedule.pop()
            
            if len(valid_schedules) >= max_schedules:
                return

    # Start backtracking with empty variable schedule
    # But first, check if fixed sections conflict with events or each other
    # (Optional validation, but good to have)
    
    backtrack(0, [])
    
    LOGGER.info(f"Generated {len(valid_schedules)} valid schedules. Missing courses: {missing_courses}")
    return valid_schedules, missing_courses

async def generate_schedule_options(request: GenerateScheduleRequest) -> GenerateScheduleResponse:
    try:
        # 1. Convert events to TimeSlots for generator
        generator_events = []
        for event in request.events:
            # Parse event times
            # Helper to parse HH:mm
            def parse_hm(t):
                if not t: return 0
                try:
                    h, m = map(int, t.split(':'))
                    return h * 60 + m
                except:
                    return 0
                
            start_min = parse_hm(event.startTime)
            end_min = parse_hm(event.endTime)
            
            if event.repeatDays:
                for day in event.repeatDays:
                    # Ensure day is a string and valid
                    if isinstance(day, str):
                        generator_events.append(TimeSlot(
                            day=day,
                            start_minutes=start_min,
                            end_minutes=end_min
                        ))
                    else:
                        LOGGER.warning(f"Invalid day format in event: {day}")

        # 2. Generate schedules
        # We limit to 10 candidates to provide more options
        candidates, missing_courses = await generate_schedules(
            request.courses,
            request.term,
            request.campus,
            events=generator_events,
            max_schedules=10
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
                if section.time_slots and len(section.time_slots) > 0:
                    # Format back to HH:mm
                    def fmt_hm(m):
                        h = m // 60
                        mn = m % 60
                        return f"{h:02d}:{mn:02d}"
                    
                    s_time = fmt_hm(section.time_slots[0].start_minutes)
                    e_time = fmt_hm(section.time_slots[0].end_minutes)
                    days = list(set(s.day for s in section.time_slots))
                elif section.section_data.startTime and section.section_data.endTime:
                    # Fallback to section data if time_slots is empty but data exists
                    s_time = section.section_data.startTime
                    e_time = section.section_data.endTime
                    days = section.section_data.repeatDays or []
                
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
    except Exception as e:
        LOGGER.error(f"Error generating schedule: {e}")
        import traceback
        traceback.print_exc()
        raise e


async def analyze_generated_schedules(request: AnalyzeSchedulesRequest) -> List[Schedule]:
    """
    Analyze a list of schedules using the AI agent to calculate difficulty, time load, etc.
    """
    # Limit concurrency to avoid hitting OpenAI Rate Limits (TPM)
    # 3 concurrent tasks is a safe balance for Tier 1 accounts (30k TPM)
    concurrency_limit = asyncio.Semaphore(3)

    async def analyze_one(schedule: Schedule):
        async with concurrency_limit:
            if not schedule.courses:
                LOGGER.info(f"Skipping analysis for empty schedule {schedule.id}")
                return schedule

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
            
            for attempt in range(3):
                try:
                    LOGGER.info(f"Starting analysis for schedule {schedule.id} with {len(schedule_tuples)} courses (Attempt {attempt+1})")
                    result = await schedule_grading_graph.ainvoke(initial_state)
                    score: ScheduleScore = result.get("schedule_score")
                    
                    if score:
                        LOGGER.info(f"Analysis complete for schedule {schedule.id}. Score: {score.adjusted_difficulty}")
                        
                        # Populate grading details dictionary
                        schedule.gradingDetails = {
                            "summary": score.summary,
                            "adjusted_difficulty": score.adjusted_difficulty,
                            "adjusted_assessment_intensity": score.adjusted_assessment_intensity,
                            "adjusted_project_intensity": score.adjusted_project_intensity,
                            "time_load": score.time_load,
                            "adjusted_rigor": score.adjusted_rigor,
                            "constraints": score.constraints,
                            "confidence": score.confidence
                        }
                        
                        # Populate top-level convenience fields
                        schedule.difficultyScore = score.adjusted_difficulty
                        schedule.weeklyHours = score.time_load
                        schedule.creditHours = score.total_credit_hours
                        
                        # Update individual course scores
                        if score.class_scores:
                            LOGGER.info(f"Updating {len(score.class_scores)} course scores for schedule {schedule.id}")
                            for course in schedule.courses:
                                # Normalize course info to match agent's keys
                                c_id = course.courseId.replace(" ", "").lower() if course.courseId else ""
                                t_name = course.instructor.replace(" ", "").lower() if course.instructor else "unknown"

                                # Create string key and lookup directly (O(1) instead of O(n))
                                class_key = create_class_key(c_id, t_name)
                                class_score = score.class_scores.get(class_key)

                                if class_score:
                                    course.difficultyRating = class_score.score
                                    course.ratingDetails = class_score.model_dump()
                                else:
                                    LOGGER.warning(f"No score found for {class_key}")
                        else:
                            LOGGER.warning(f"No class scores returned for schedule {schedule.id}")
                        
                        # If successful, break the retry loop
                        break
                    else:
                        LOGGER.warning(f"No score object returned for schedule {schedule.id}")
                        # If no score but no exception, maybe we shouldn't retry? 
                        # But let's retry just in case it was a glitch.
                except Exception as e:
                    LOGGER.error(f"Error analyzing schedule {schedule.id} (Attempt {attempt+1}): {e}")
                    if attempt == 2:
                        import traceback
                        traceback.print_exc()
                    else:
                        await asyncio.sleep(1)
                
            return schedule

    # Run schedule analyses in parallel
    tasks = [analyze_one(s) for s in request.schedules]
    analyzed_schedules = await asyncio.gather(*tasks)
    
    return analyzed_schedules

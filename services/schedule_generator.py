import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel

from services.osu_course_search import fetch_osu_course_sections, CourseSection

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

from schemas.schedule import Course

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

    # 2. Fetch sections for variable courses
    tasks = []
    for code in variable_courses:
        parts = code.split()
        if len(parts) >= 2:
            subject = parts[0]
            number = parts[1]
            tasks.append(fetch_osu_course_sections(subject, number, term=term, campus=campus))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    course_sections_map: Dict[str, List[ParsedSection]] = {}
    missing_courses: List[str] = []
    
    for i, res in enumerate(results):
        code = variable_courses[i]
        if isinstance(res, Exception):
            print(f"Error fetching {code}: {res}")
            missing_courses.append(code)
            continue
            
        # Parse sections
        parsed_sections = []
        for sec in res.sections:
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
            
            parsed_sections.append(ParsedSection(
                course_subject=res.subject,
                course_number=res.course_number,
                section_data=sec,
                time_slots=slots
            ))
        
        if parsed_sections:
            course_sections_map[code] = parsed_sections
        else:
            print(f"No sections found for {code}")
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
    
    return valid_schedules, missing_courses

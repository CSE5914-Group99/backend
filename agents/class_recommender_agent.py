from dotenv import load_dotenv
load_dotenv()

import json
from pydantic import BaseModel, Field
from typing import Optional, TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Send
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

# Import models and graphs from other agents
from .class_grading_agent import ClassScore, class_grading_graph
from .schedule_grading_agent import ClassTeacherTuple, ScheduleScore

# Import session factory for creating new sessions in parallel operations
from db.session import get_session_factory

# Import tools
from .tools.internet_search import basic_tavily_search
from .tools.osu_course_search import osu_course_search_tool
from .tools.rate_my_professor import rate_my_professor_tool

# Tool for grading a class (used by search agent to compare difficulties)
@tool
async def grade_class_tool(class_id: str, teacher: str = "unknown") -> str:
    """
    Get the difficulty score for a specific class and teacher combination.
    Use this to compare the difficulty of current schedule classes with potential alternatives.

    Args:
        class_id: The class ID (e.g., "CSE 2331", "MATH 1151")
        teacher: The teacher's name (e.g., "John Smith"). Use "unknown" if not specified.

    Returns:
        A summary of the class difficulty including score, time load, and key metrics.
    """
    # Normalize inputs
    normalized_class_id = class_id.replace(" ", "").lower()
    normalized_teacher = teacher.replace(" ", "").lower() if teacher else "unknown"

    message_content = f"Evaluate the class {class_id}"
    if teacher and teacher != "unknown":
        message_content += f" taught by Professor {teacher}"

    # Create a new session for this operation
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await class_grading_graph.ainvoke({
            "messages": [HumanMessage(content=message_content)],
            "class_name": normalized_class_id,
            "teacher_name": normalized_teacher,
            "class_score": None,
            "cached": False,
            "session": session
        })

    class_score = result.get("class_score")

    if class_score:
        return f"""Class: {class_id} (Teacher: {teacher})
Difficulty Score: {class_score.score}/100
Credit Hours: {class_score.ch}
Time Load: {class_score.time_load} hrs/week
Rigor: {class_score.rigor}/100
Assessment Intensity: {class_score.assessment_intensity}/100
Project Intensity: {class_score.project_intensity}/100
Summary: {class_score.summary}
Confidence: {class_score.confidence}"""
    else:
        return f"Could not retrieve difficulty score for {class_id} with {teacher}"

# Pydantic model for a single time slot
class TimeSlot(BaseModel):
    start_time: str = Field(description="Start time in HH:mm format (e.g., '10:00', '14:30')")
    end_time: str = Field(description="End time in HH:mm format (e.g., '10:55', '15:45')")
    repeat_days: list[str] = Field(description="List of days the class meets (e.g., ['Monday', 'Wednesday', 'Friday'])")

# Pydantic model for a class with time information
class ScheduleClassWithTime(BaseModel):
    class_id: str = Field(description="The class ID (e.g., 'CSE 2331')")
    teacher: Optional[str] = Field(default=None, description="The teacher name")
    time_slots: list[TimeSlot] = Field(default_factory=list, description="List of time slots when this class meets")

# Pydantic model for a modification request
class ModificationRequest(BaseModel):
    class_to_replace: Optional[str] = Field(default=None, description="Class ID to replace (None if adding a new class)")
    reason: str = Field(description="Why this modification is needed (e.g., 'too difficult', 'schedule conflict', 'need GE credit')")
    criteria: str = Field(description="Criteria for the new/replacement class (e.g., 'easier', 'morning only', 'fulfills GE diversity requirement')")

# Pydantic model for a potential alternative class found during search
class AlternativeClass(BaseModel):
    class_id: str = Field(description="The class ID")
    teacher: Optional[str] = Field(default=None, description="Recommended teacher")
    time_slots: list[TimeSlot] = Field(default_factory=list, description="Meeting time slots")
    for_replacement: str = Field(description="Which class this is an alternative for")

# Pydantic model for search results
class AlternativeSearchResult(BaseModel):
    alternatives: list[AlternativeClass] = Field(description="List of potential alternative classes")
    search_notes: str = Field(description="Notes about the search process")

# Pydantic model for class info in recommendations
class ClassInfo(BaseModel):
    class_id: str = Field(description="The class ID (e.g., 'CSE 2221')")
    teacher: Optional[str] = Field(default=None, description="Recommended teacher")
    time_slots: list[TimeSlot] = Field(default_factory=list, description="Meeting time slots")
    class_score: ClassScore = Field(description="Full difficulty scoring from the class grading agent")
    why_recommended: str = Field(description="Why this class fits the criteria")

# Pydantic model for a schedule alteration option
class ScheduleAlteration(BaseModel):
    alteration_name: str = Field(description="Short name for this alteration (e.g., 'Easier Option', 'Morning Schedule')")
    description: str = Field(description="Description of what this alteration achieves")
    classes_to_remove: list[str] = Field(description="List of class IDs to remove from the schedule")
    classes_to_add: list[ClassInfo] = Field(description="List of classes to add with full info")
    estimated_difficulty_change: int = Field(description="Estimated change in overall difficulty (-100 to +100)")
    estimated_time_change: float = Field(description="Estimated change in weekly hours")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this recommendation")
    warnings: list[str] = Field(default_factory=list, description="Any warnings or considerations")

# Pydantic model for the recommender output
class RecommenderOutput(BaseModel):
    alterations: list[ScheduleAlteration] = Field(description="List of possible schedule alterations")
    overall_summary: str = Field(description="Summary of all recommendations and advice")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall confidence in recommendations")

# Helper function to convert HH:mm to minutes from midnight
def time_to_minutes(time_str: str) -> int:
    """Convert HH:mm format to minutes from midnight"""
    hours, mins = map(int, time_str.split(":"))
    return hours * 60 + mins

# Helper function to check if two time slots conflict
def slots_conflict(slot1: TimeSlot, slot2: TimeSlot) -> bool:
    """Check if two time slots conflict (overlapping days and times)"""
    # Check if any days overlap
    common_days = set(slot1.repeat_days) & set(slot2.repeat_days)
    if not common_days:
        return False

    # Convert times to minutes for comparison
    start1 = time_to_minutes(slot1.start_time)
    end1 = time_to_minutes(slot1.end_time)
    start2 = time_to_minutes(slot2.start_time)
    end2 = time_to_minutes(slot2.end_time)

    # Check if time ranges overlap
    return not (end1 <= start2 or end2 <= start1)

# Helper function to check if a class conflicts with a list of time slots
def class_conflicts_with_slots(class_slots: list[TimeSlot], existing_slots: list[TimeSlot]) -> bool:
    """Check if any of the class's time slots conflict with existing slots"""
    for class_slot in class_slots:
        for existing_slot in existing_slots:
            if slots_conflict(class_slot, existing_slot):
                return True
    return False

# Helper function to format time slots for display
def format_time_slots(slots: list[TimeSlot]) -> str:
    """Format time slots into a readable string"""
    if not slots:
        return "TBD"

    parts = []
    for slot in slots:
        days_str = "/".join(day[:3] for day in slot.repeat_days)
        time_str = f"{days_str} {slot.start_time}-{slot.end_time}"
        parts.append(time_str)

    return ", ".join(parts)

# Reducer for merging graded alternatives
def merge_graded_alternatives(left: dict | None, right: dict | None) -> dict:
    if left is None:
        return right or {}
    if right is None:
        return left
    return {**left, **right}

# Define the state for the recommender graph
class RecommenderState(TypedDict):
    messages: Annotated[list, add_messages]
    schedule: list[ScheduleClassWithTime]
    schedule_score: ScheduleScore
    modification_requests: list[ModificationRequest]
    alternatives_found: list[AlternativeClass] | None
    feasible_alternatives: list[AlternativeClass] | None
    graded_alternatives: Annotated[dict, merge_graded_alternatives]
    recommender_output: RecommenderOutput | None
    session: AsyncSession | None

# Prompt for finding alternatives
find_alternatives_prompt = '''
You are an expert Ohio State University academic advisor. Your job is to search for potential alternative classes based on student needs.

## Your Task
Search for alternative classes that could replace or be added to a student's schedule based on their modification requests.

## Available Tools
- **osu_course_search_tool**: Search OSU's course catalog for available classes
- **rate_my_professor_tool**: Look up professor ratings
- **basic_tavily_search**: Search web for course discussions and reviews
- **grade_class_tool**: Get difficulty scores for a class/teacher combination. Use this to:
  - Check the difficulty of classes currently in the schedule
  - Compare difficulty between the current class and potential alternatives
  - Find easier sections taught by different teachers

## Search Strategy
For each modification request:
1. First, use grade_class_tool to get the difficulty of the class being replaced (so you know what to compare against)
2. Search for 4-6 potential alternatives that match the criteria
3. Get specific section times from OSU course search
4. Note which professors are well-rated
5. Optionally use grade_class_tool to quickly compare difficulty of alternatives

## IMPORTANT: Different Sections and Teachers
- If the student wants an easier version of a class, look for different SECTIONS with different teachers
- The same class taught by different professors can have very different difficulty levels
- Include multiple sections of the same class with different teachers as separate alternatives
- Example: CSE 2221 with Prof. Smith AND CSE 2221 with Prof. Jones are both valid alternatives

## Database ID Format
When providing alternatives, use these formats for proper database lookup:
- **class_id**: Use the course number format (e.g., "CSE 2221", "MATH 1151")
- **teacher**: Use the teacher's full name as it appears (e.g., "John Smith", "Mary Johnson")
  - Teacher names are used as identifiers to look up class difficulty data
  - Be consistent with name formatting (First Last)

## Time Slot Format
For each alternative, provide time_slots as a list with:
- start_time: Time in HH:mm format (e.g., "10:00", "14:30")
- end_time: Time in HH:mm format (e.g., "10:55", "15:45")
- repeat_days: List of day names (e.g., ["Monday", "Wednesday", "Friday"])

Example: A class at MWF 10:00-10:55 would have time_slots:
[{"start_time": "10:00", "end_time": "10:55", "repeat_days": ["Monday", "Wednesday", "Friday"]}]

Example: A class at TR 9:35-10:55 would have time_slots:
[{"start_time": "09:35", "end_time": "10:55", "repeat_days": ["Tuesday", "Thursday"]}]

Find 4-6 alternatives per replacement request. Include different options (different sections, different professors, different but equivalent classes).
'''

# Prompt for generating final alterations
generate_alterations_prompt = '''
You are an expert Ohio State University academic advisor analyzing graded alternatives to create schedule modification options.

## Your Task
Using the graded alternatives provided, create 2-4 schedule alteration options for the student.

## Input
You will receive:
1. Current schedule with times
2. Schedule summary (difficulty metrics)
3. Modification requests
4. Graded alternatives with full difficulty metrics

## Output Requirements
Create 2-4 alteration options, each with:
- **alteration_name**: Clear name (e.g., "Easiest Option", "Best Rated", "Morning Schedule")
- **description**: What this achieves
- **classes_to_remove**: Class IDs being removed
- **classes_to_add**: For each class include:
  - class_id, teacher, time_slots
  - class_score: The full ClassScore object with score, ch, summary, time_load, rigor, assessment_intensity, project_intensity, pace, pre_reqs, co_reqs, tags, evidence_snippets, confidence
  - why_recommended
- **estimated_difficulty_change**: Impact on overall schedule difficulty
- **estimated_time_change**: Impact on weekly hours
- **confidence**: Based on grade confidence
- **warnings**: Prerequisites, enrollment concerns, etc.

## Guidelines
- Use the actual graded scores, don't estimate
- Consider different criteria: easiest, best-rated, best schedule fit
- If no good alternatives exist, explain why
- Warn about prerequisites and potential issues
'''

# Initialize the agents
llm = ChatOpenAI(model="gpt-5-mini", temperature=1)

search_tools = [
    basic_tavily_search,
    osu_course_search_tool,
    rate_my_professor_tool,
    grade_class_tool,
]

find_alternatives_agent = create_react_agent(
    model=llm,
    tools=search_tools,
    prompt=find_alternatives_prompt,
    response_format=AlternativeSearchResult
)

generate_alterations_agent = create_react_agent(
    model=llm,
    tools=[],
    prompt=generate_alterations_prompt,
    response_format=RecommenderOutput
)

# Node 1: Find all alternatives for all replacement requests
async def find_all_alternatives(state: RecommenderState) -> dict:
    schedule = state.get("schedule", [])
    modification_requests = state.get("modification_requests", [])

    # Build context message
    schedule_info = "## Current Schedule\n\n"
    for cls in schedule:
        teacher_str = f" - Prof. {cls.teacher}" if cls.teacher else ""
        times_str = f" ({format_time_slots(cls.time_slots)})" if cls.time_slots else ""
        schedule_info += f"- **{cls.class_id}**{teacher_str}{times_str}\n"

    requests_info = "\n## Modification Requests\n\n"
    for i, req in enumerate(modification_requests, 1):
        if req.class_to_replace:
            requests_info += f"### {i}. Replace {req.class_to_replace}\n"
        else:
            requests_info += f"### {i}. Add a new class\n"
        requests_info += f"- **Reason**: {req.reason}\n"
        requests_info += f"- **Criteria**: {req.criteria}\n\n"

    message_content = f"""{schedule_info}
{requests_info}

Please search for 4-6 potential alternatives for each modification request. Include specific times and teachers if possible.
"""

    message = HumanMessage(content=message_content)
    response = await find_alternatives_agent.ainvoke(
        {"messages": [message]},
        config={"recursion_limit": 50},
        debug=False
    )

    search_result: AlternativeSearchResult = response['structured_response']

    return {
        "messages": response["messages"],
        "alternatives_found": search_result.alternatives
    }

# Node 2: Filter out alternatives with time conflicts
def filter_time_conflicts(state: RecommenderState) -> dict:
    schedule = state.get("schedule", [])
    alternatives = state.get("alternatives_found", [])
    modification_requests = state.get("modification_requests", [])

    if not alternatives:
        return {"feasible_alternatives": []}

    # Get classes to replace
    classes_to_replace = {
        req.class_to_replace.replace(" ", "").lower()
        for req in modification_requests
        if req.class_to_replace
    }

    # Get time slots of remaining classes (not being replaced)
    remaining_slots = []
    for cls in schedule:
        class_id_normalized = cls.class_id.replace(" ", "").lower()
        if class_id_normalized not in classes_to_replace:
            remaining_slots.extend(cls.time_slots)

    # Filter alternatives
    feasible = []
    for alt in alternatives:
        if not alt.time_slots:
            # No time info, assume feasible
            feasible.append(alt)
            continue

        # Check for conflicts with remaining classes
        if not class_conflicts_with_slots(alt.time_slots, remaining_slots):
            feasible.append(alt)

    return {"feasible_alternatives": feasible}

# Node 3: Grade a single alternative class
async def grade_alternative(state: dict) -> dict:
    alt = state["alternative"]

    # Normalize inputs
    normalized_class_id = alt.class_id.replace(" ", "").lower()
    normalized_teacher = alt.teacher.replace(" ", "").lower() if alt.teacher else "unknown"

    message_content = f"Evaluate the class {alt.class_id}"
    if alt.teacher:
        message_content += f" taught by Professor {alt.teacher}"

    # Create a new session for this parallel operation to avoid concurrent session errors
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await class_grading_graph.ainvoke({
            "messages": [HumanMessage(content=message_content)],
            "class_name": normalized_class_id,
            "teacher_name": normalized_teacher,
            "class_score": None,
            "cached": False,
            "session": session
        })

    class_score = result.get("class_score")

    # Create key for this alternative
    time_key = json.dumps([{"start": s.start_time, "end": s.end_time, "days": s.repeat_days} for s in alt.time_slots])
    key = f"{normalized_class_id}|{normalized_teacher}|{time_key}"

    if class_score:
        return {
            "graded_alternatives": {
                key: {
                    "class_id": alt.class_id,
                    "teacher": alt.teacher,
                    "time_slots": alt.time_slots,
                    "for_replacement": alt.for_replacement,
                    "score": class_score
                }
            }
        }
    else:
        return {"graded_alternatives": {}}

# Node 4: Join graded results
def join_grades(state: RecommenderState) -> dict:
    return {}

# Node 5: Generate final alteration options
async def generate_alterations(state: RecommenderState) -> dict:
    schedule = state.get("schedule", [])
    schedule_score = state.get("schedule_score")
    modification_requests = state.get("modification_requests", [])
    graded_alternatives = state.get("graded_alternatives", {})

    if not graded_alternatives:
        return {
            "recommender_output": RecommenderOutput(
                alterations=[],
                overall_summary="No suitable alternatives were found that don't conflict with your existing schedule.",
                confidence=0.0
            )
        }

    # Build context for the agent
    schedule_info = "## Current Schedule\n\n"
    for cls in schedule:
        teacher_str = f" - Prof. {cls.teacher}" if cls.teacher else ""
        times_str = f" ({format_time_slots(cls.time_slots)})" if cls.time_slots else ""
        schedule_info += f"- **{cls.class_id}**{teacher_str}{times_str}\n"

    summary_info = f"""
## Schedule Summary
- Total Credit Hours: {schedule_score.total_credit_hours}
- Number of Classes: {schedule_score.num_classes}
- Overall Difficulty: {schedule_score.adjusted_difficulty}/100
- Time Load: {schedule_score.time_load} hrs/week
"""

    requests_info = "\n## Modification Requests\n\n"
    for i, req in enumerate(modification_requests, 1):
        if req.class_to_replace:
            requests_info += f"### {i}. Replace {req.class_to_replace}\n"
        else:
            requests_info += f"### {i}. Add a new class\n"
        requests_info += f"- **Reason**: {req.reason}\n"
        requests_info += f"- **Criteria**: {req.criteria}\n\n"

    # Build graded alternatives info
    graded_info = "\n## Graded Alternatives\n\n"
    for key, data in graded_alternatives.items():
        score = data["score"]
        teacher_str = f" (Prof. {data['teacher']})" if data.get('teacher') else ""
        times_str = f" - {format_time_slots(data['time_slots'])}" if data.get('time_slots') else ""

        graded_info += f"### {data['class_id']}{teacher_str}{times_str}\n"
        graded_info += f"- **For replacing**: {data['for_replacement']}\n"
        graded_info += f"- **Difficulty Score**: {score.score}/100\n"
        graded_info += f"- **Credit Hours**: {score.ch}\n"
        graded_info += f"- **Time Load**: {score.time_load} hrs/week\n"
        graded_info += f"- **Rigor**: {score.rigor}/100\n"
        graded_info += f"- **Assessment Intensity**: {score.assessment_intensity}/100\n"
        graded_info += f"- **Project Intensity**: {score.project_intensity}/100\n"
        graded_info += f"- **Summary**: {score.summary}\n"
        graded_info += f"- **Confidence**: {score.confidence}\n\n"

    message_content = f"""{schedule_info}
{summary_info}
{requests_info}
{graded_info}

Based on the graded alternatives above, create 2-4 schedule alteration options.
"""

    message = HumanMessage(content=message_content)
    response = await generate_alterations_agent.ainvoke(
        {"messages": [message]},
        config={"recursion_limit": 50},
        debug=False
    )

    return {
        "messages": response["messages"],
        "recommender_output": response['structured_response']
    }

# Build the graph
def create_class_recommender_graph():
    graph = StateGraph(RecommenderState)

    # Add nodes
    graph.add_node("find_all_alternatives", find_all_alternatives)
    graph.add_node("filter_time_conflicts", filter_time_conflicts)
    graph.add_node("grade_alternative", grade_alternative)
    graph.add_node("join_grades", join_grades)
    graph.add_node("generate_alterations", generate_alterations)

    # Fan out function for parallel grading
    def fan_out_grading(state: RecommenderState):
        feasible = state.get("feasible_alternatives", [])
        session = state.get("session")

        if not feasible:
            return [Send("join_grades", state)]

        send_objects = []
        for alt in feasible:
            send_objects.append(
                Send(
                    "grade_alternative",
                    {
                        "alternative": alt,
                        "session": session
                    }
                )
            )

        return send_objects

    # Add edges
    graph.add_edge(START, "find_all_alternatives")
    graph.add_edge("find_all_alternatives", "filter_time_conflicts")
    graph.add_conditional_edges("filter_time_conflicts", fan_out_grading)
    graph.add_edge("grade_alternative", "join_grades")
    graph.add_edge("join_grades", "generate_alterations")
    graph.add_edge("generate_alterations", END)

    return graph.compile()

# Create the compiled graph
class_recommender_graph = create_class_recommender_graph()

if __name__ == "__main__":
    # run with python -m agents.class_recommender_agent
    import asyncio

    # Test data with standardized time slots
    test_schedule = [
        ScheduleClassWithTime(
            class_id="CSE 2331",
            teacher="Smith",
            time_slots=[
                TimeSlot(start_time="10:00", end_time="10:55", repeat_days=["Monday", "Wednesday", "Friday"])
            ]
        ),
        ScheduleClassWithTime(
            class_id="MATH 2568",
            teacher=None,
            time_slots=[
                TimeSlot(start_time="09:35", end_time="10:55", repeat_days=["Tuesday", "Thursday"])
            ]
        ),
        ScheduleClassWithTime(
            class_id="PHYSICS 1250",
            teacher="Johnson",
            time_slots=[
                TimeSlot(start_time="12:00", end_time="12:55", repeat_days=["Monday", "Wednesday", "Friday"])
            ]
        )
    ]

    # Create a mock ScheduleScore
    test_schedule_score = ScheduleScore(
        class_scores={},
        total_credit_hours=12,
        num_classes=3,
        summary="A moderately challenging STEM-focused schedule.",
        adjusted_difficulty=68,
        adjusted_assessment_intensity=72,
        adjusted_project_intensity=55,
        time_load=18.5,
        adjusted_rigor=70,
        contraints="Working 15 hours per week",
        confidence=0.7
    )

    test_modifications = [
        ModificationRequest(
            class_to_replace="CSE 2331",
            reason="Too difficult for my current workload",
            criteria="Easier CSE class that counts toward major, morning availability"
        )
    ]

    initial_state = {
        "messages": [],
        "schedule": test_schedule,
        "schedule_score": test_schedule_score,
        "modification_requests": test_modifications,
        "alternatives_found": None,
        "feasible_alternatives": None,
        "graded_alternatives": {},
        "recommender_output": None,
        "session": None
    }

    async def run_test():
        print("Testing Class Recommender Agent")
        print("=" * 50)
        print(f"\nCurrent Schedule:")
        for cls in test_schedule:
            print(f"  - {cls.class_id} ({format_time_slots(cls.time_slots)})")
        print(f"\nSchedule Difficulty: {test_schedule_score.adjusted_difficulty}/100")
        print(f"\nModification: Replace {test_modifications[0].class_to_replace}")
        print(f"Criteria: {test_modifications[0].criteria}")
        print("\nSearching and grading alternatives...\n")

        result = await class_recommender_graph.ainvoke(initial_state, debug=False)

        print("\n=== Class Recommender Results ===\n")

        if result.get("recommender_output"):
            output = result["recommender_output"]
            print(f"Overall Confidence: {output.confidence:.0%}")
            print(f"\n{output.overall_summary}")

            for i, alt in enumerate(output.alterations, 1):
                print(f"\n--- Option {i}: {alt.alteration_name} ---")
                print(f"Description: {alt.description}")
                print(f"Remove: {', '.join(alt.classes_to_remove) if alt.classes_to_remove else 'None'}")
                print(f"Add:")
                for cls in alt.classes_to_add:
                    score = cls.class_score
                    print(f"  - {cls.class_id} ({score.ch} cr, {score.score}/100 difficulty)")
                    print(f"    Teacher: {cls.teacher or 'TBD'}")
                    print(f"    Times: {format_time_slots(cls.time_slots)}")
                    print(f"    Time Load: {score.time_load} hrs/week")
                    print(f"    Rigor: {score.rigor}/100, Assessment: {score.assessment_intensity}/100")
                    print(f"    Summary: {score.summary[:100]}...")
                    print(f"    Why: {cls.why_recommended}")
                print(f"Difficulty Change: {alt.estimated_difficulty_change:+d}")
                print(f"Time Change: {alt.estimated_time_change:+.1f} hrs/week")
                print(f"Confidence: {alt.confidence:.0%}")
                if alt.warnings:
                    print(f"Warnings: {', '.join(alt.warnings)}")
        else:
            print("No recommendations generated")

    asyncio.run(run_test())

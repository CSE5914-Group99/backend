from dotenv import load_dotenv
load_dotenv()

from pydantic import BaseModel, Field
from typing import Optional, TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

# Import tools
# Use relative import so deployment does not treat tools as top-level package
from .tools.internet_search import basic_tavily_search
from .tools.osu_course_search import osu_course_search_tool
from .tools.rate_my_professor import rate_my_professor_tool
from .tools.reddit_search import reddit_search_tool
#from .tools.osu_search import osu_search
#from .tools.coursicle_search import coursicle_search

# Import CRUD functions for caching
import sys
from pathlib import Path
# Add backend directory to path if not already there
backend_path = str(Path(__file__).parent.parent)
if backend_path not in sys.path:
    sys.path.append(backend_path)
from services.schedule_service import upsert_courses
from schemas.schedule import Course as CourseSchema

prompt = '''
You are an expert Ohio State University class difficulty analyzer. Your job is to research and evaluate the difficulty of OSU classes to help students make informed course selection decisions.

## Your Task
Analyze the given class and provide a comprehensive difficulty assessment using multiple metrics. Be objective, evidence-based, and student-focused.

**IMPORTANT**: If a specific instructor/professor name is provided, you MUST factor in instructor-specific information. The same course can vary significantly in difficulty depending on who teaches it.

## Research Process
1. **Search for information** about the class using available tools:
   - Course syllabi, descriptions, and requirements
   - **If instructor is provided**: Search specifically for that instructor's teaching style, grading policies, and student reviews
   - Student reviews and experiences (Reddit, RateMyProfessor, Coursicle)
   - Official OSU course catalogs and department resources
   - Discussion forums and student communities

2. **Collect evidence**: Save direct quotes and snippets from your sources that support your scoring decisions
   - **If instructor is provided**: Prioritize instructor-specific reviews and feedback

3. **Analyze holistically**: Consider workload, conceptual difficulty, assessment burden, pacing, and student feedback
   - **If instructor is provided**: Weight instructor-specific factors heavily in your assessment (teaching clarity, grading strictness, assignment load, exam difficulty)

## Scoring Guidelines
**Note**: If an instructor is specified, adjust all scores based on that instructor's teaching style, grading policies, and workload expectations.

### Overall Score (1-100)
Holistic difficulty score combining all factors:
- 1-20: Very easy, minimal effort
- 21-40: Easy, manageable workload
- 41-60: Moderate, average college course
- 61-80: Challenging, requires significant effort
- 81-100: Extremely difficult, demanding course
- **With instructor**: Reflect instructor-specific difficulty variations (same course can be 40 with one prof, 80 with another)

### Time Load (0.0-8.0)
How many credit hours does this class FEEL like in terms of weekly time commitment?
- If a 3-credit class feels like 3 hours/week → score ~3.0
- If it feels like 6 hours/week → score ~6.0
- Consider: homework, studying, projects, reading
- **With instructor**: Factor in instructor's assignment load and grading expectations

### Rigor (0-100)
Conceptual and technical depth:
- 0-30: Memorization-based, straightforward concepts
- 31-60: Moderate analytical thinking required
- 61-100: Deep theoretical understanding, complex problem-solving
- **With instructor**: Consider how deeply instructor covers material vs surface-level treatment

### Assessment Intensity (0-100)
Frequency and difficulty of exams/quizzes:
- Consider: number of exams, cumulative vs non-cumulative, difficulty level, time pressure
- 0-30: Few, straightforward assessments
- 31-60: Regular exams of moderate difficulty
- 61-100: Frequent, high-stakes, difficult exams
- **With instructor**: This varies SIGNIFICANTLY by instructor - prioritize instructor-specific exam difficulty

### Project Intensity (0-100)
Complexity and time requirements for projects/assignments:
- 0-30: Light homework, simple assignments
- 31-60: Moderate projects, regular homework
- 61-100: Major projects, extensive coding/writing/research
- **With instructor**: Factor in instructor's project requirements and grading strictness

### Pace (0-100)
Speed of material coverage:
- 0-30: Slow, plenty of review time
- 31-60: Moderate, steady progression
- 61-100: Fast, covers large amounts quickly
- **With instructor**: Reflect instructor's teaching pace and time management

### Prerequisites & Co-requisites
List the required and recommended prerequisite/co-requisite courses.

## Summary Guidelines
- **With instructor**: Mention instructor-specific characteristics (e.g., "Prof. Smith's section is known for rigorous exams but clear lectures")
- **Without instructor**: Provide general course overview across all instructors
- Keep it concise (2-3 sentences max)

## Evidence Requirements
- **Tags**: Add descriptive tags (e.g., "math-heavy", "project-based", "memorization", "time-consuming", "well-taught")
  - **If instructor provided**: Add instructor-specific tags (e.g., "smith-tough-grader", "jones-great-teacher")
- **Evidence Snippets**: Include 3-5 direct quotes from student reviews or course materials that justify your scores
  - **If instructor provided**: Prioritize quotes specifically mentioning that instructor
- **Confidence**: Rate your confidence (0.0-1.0) based on:
  - 0.0-0.4: Very limited data, mostly guessing
  - 0.5-0.7: Some data available, reasonable estimate
  - 0.8-1.0: Abundant reliable data, high confidence
  - **Lower confidence if instructor is specified but no instructor-specific data is found**

## Important Notes
- **Instructor matters**: The same course can range from easy to extremely difficult depending on the instructor
- Be objective: Balance course content difficulty with instructor-specific factors
- Acknowledge uncertainty: If data is sparse, lower your confidence score
- Look for patterns: Multiple students mentioning the same issues carries more weight
- Consider recency: Recent reviews are more relevant than old ones
- Context matters: Difficulty is relative to the student's background and major

Now, research the class and provide your comprehensive difficulty assessment.
'''

# Scoring fields for the classes
class ClassScore(BaseModel):
    score: int = Field(ge=1, le=100, description="overall class difficulty score")
    ch: int = Field(description="credit hours of course")
    summary: str = Field(description="overall summary of class difficulty")
    time_load: float = Field(ge=0, le=8, description="weekly time/effort vibe, how many credit hours it feels like for this class.")
    rigor: int = Field(0, ge=0, le=100, description="conceptual/technical depth")
    assessment_intensity: int = Field(0, ge=0, le=100, description="amount and difficulty of exams")
    project_intensity: int = Field(0, ge=0, le=100, description="amount and difficulty of projects")
    pace: int = Field(50, ge=0, le=100, description="pace of class")
    pre_reqs: list[str] = Field(description="list of pre-req classes needed")
    co_reqs: list[str] = Field(description="list of co-req classes needed")
    
    # Evidence
    tags: list[str] = Field(default_factory=list, description="tags about class")
    evidence_snippets: list[str] = Field(default_factory=list, description="direct snippets from online posts")
    confidence: float = Field(0.6, ge=0.0, le=1.0, description="confidence about class score (more data online = more sure about assigned score)")

# Define the state for the graph
class ClassGradingState(TypedDict):
    messages: Annotated[list, add_messages]
    class_name: str
    teacher_name: str | None
    class_score: ClassScore | None
    cached: bool
    session: AsyncSession | None  # Database session for caching

# Initialize the LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0)

from sqlalchemy import select, func
from db.models import Course
import asyncio
import re
from langchain_core.messages import SystemMessage, HumanMessage

# Node 1: Check cache for class info
async def check_cache(state: ClassGradingState) -> ClassGradingState:
    """Check if class information is already cached in the database (Course table)"""
    session = state.get("session")
    class_name_input = state.get("class_name") 
    teacher_name_input = state.get("teacher_name")

    if not session:
        return {"cached": False, "class_score": None}

    # Normalize for query matching
    class_name_norm = class_name_input.replace(" ", "").lower() if class_name_input else ""
    teacher_name_norm = teacher_name_input.replace(" ", "").lower() if teacher_name_input else "unknown"

    try:
        # Query Course for any entry with matching course_id and teacher_name that has rating_details
        # We need to normalize the DB values to match the input state
        stmt = select(Course.rating_details).where(
            func.replace(func.lower(Course.course_id), ' ', '') == class_name_norm,
            func.replace(func.lower(Course.teacher_name), ' ', '') == teacher_name_norm,
            Course.rating_details.is_not(None)
        ).limit(1)
        
        result = await session.execute(stmt)
        rating_details = result.scalar_one_or_none()

        if rating_details:
            print(f"Cache HIT for {class_name_norm} / {teacher_name_norm}")
            # Found cached data - convert JSON to ClassScore
            class_score = ClassScore(**rating_details)
            return {
                "cached": True,
                "class_score": class_score
            }
        else:
            print(f"Cache MISS for {class_name_norm} / {teacher_name_norm}")
    except Exception as e:
        # If cache lookup fails, continue to agent
        print(f"Cache lookup error: {e}")

    # No cache found or error occurred
    return {
        "cached": False,
        "class_score": None
    }

# Node 2: Gather Info (Parallel)
async def gather_info(state: ClassGradingState) -> ClassGradingState:
    """Run all search tools in parallel to gather context"""
    class_name = state["class_name"]
    teacher_name = state.get("teacher_name")
    
    # Parse class name (e.g. "CSE 2331" -> "CSE", "2331")
    subject = ""
    number = ""
    # Handle "CSE2331" or "CSE 2331"
    match = re.match(r"([A-Za-z]+)\s*(\d+)", class_name)
    if match:
        subject = match.group(1)
        number = match.group(2)
    
    tasks = []
    
    # 1. OSU Search
    if subject and number:
        tasks.append(osu_course_search_tool.ainvoke({
            "subject": subject,
            "course_number": number,
            "term": "Summer 2025", 
            "campus": "Columbus"
        }))
    else:
        tasks.append(asyncio.sleep(0)) # No-op placeholder

    # 2. RMP
    if teacher_name and teacher_name.lower() != "unknown":
        tasks.append(rate_my_professor_tool.ainvoke({"query": teacher_name}))
    else:
        tasks.append(asyncio.sleep(0))

    # 3. Reddit
    if subject and number:
        t_name = teacher_name if teacher_name and teacher_name.lower() != "unknown" else ""
        tasks.append(reddit_search_tool.ainvoke({
            "course_number": f"{subject} {number}",
            "teacher_name": t_name
        }))
    else:
        tasks.append(asyncio.sleep(0))

    # 4. Tavily
    query = f"Ohio State University {class_name} difficulty"
    if teacher_name and teacher_name.lower() != "unknown":
        query += f" {teacher_name}"
    tasks.append(basic_tavily_search.ainvoke({"query": query}))

    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Helper to safely get result
    def get_result(idx):
        res = results[idx]
        if isinstance(res, Exception):
            return f"Error fetching data: {str(res)}"
        return res
    
    # Unpack results (handling the placeholders)
    osu_res = get_result(0) if (subject and number) else "Skipped (Invalid class format)"
    rmp_res = get_result(1) if (teacher_name and teacher_name.lower() != "unknown") else "Skipped (No instructor provided)"
    reddit_res = get_result(2) if (subject and number) else "Skipped"
    tavily_res = get_result(3)
    
    context = f"""
    ## Research Data Gathered
    
    **OSU Course Catalog (Sections & Availability)**:
    {osu_res}
    
    **Rate My Professor**:
    {rmp_res}
    
    **Reddit Discussions**:
    {reddit_res}
    
    **General Web Search**:
    {tavily_res}
    """
    
    # Return as a HumanMessage so the LLM sees it as input
    return {"messages": [HumanMessage(content=context)]}

# Node 3: Generate Score
async def generate_score(state: ClassGradingState) -> ClassGradingState:
    """Analyze the gathered info and generate the score"""
    # Combine the system prompt with the gathered research messages
    messages = [SystemMessage(content=prompt)] + state["messages"]
    
    # Force structured output
    structured_llm = llm.with_structured_output(ClassScore)
    response = await structured_llm.ainvoke(messages)
    
    # Cache the result if session is available
    session = state.get("session")
    if session and response:
        try:
            class_name = state.get("class_name")
            teacher_name = state.get("teacher_name")
            
            # Use schedule service upsert to maintain consistency with other routes
            # We need to handle the case where teacher_name is 'unknown' or None
            t_name = teacher_name if teacher_name and teacher_name.lower() != 'unknown' else None
            
            course_data = CourseSchema(
                courseId=class_name,
                instructor=t_name,
                rating_details=response.model_dump()
            )
            
            print(f"Caching result for {class_name} / {teacher_name}")
            await upsert_courses([course_data], session)
            
        except Exception as e:
            print(f"Error caching result: {e}")

    return {"class_score": response}

# Conditional edge, Route based on cache hit/miss
def route_after_cache_check(state: ClassGradingState) -> Literal["gather_info", "end"]:
    """Route to gather_info if no cache, otherwise end"""
    if state.get("cached") and state.get("class_score"):
        return "end"
    return "gather_info"

# Build the graph
def create_class_grading_graph():
    """Create and return the compiled class grading graph"""
    graph = StateGraph(ClassGradingState)

    # Add nodes
    graph.add_node("check_cache", check_cache)
    graph.add_node("gather_info", gather_info)
    graph.add_node("generate_score", generate_score)

    # Add edges
    graph.add_edge(START, "check_cache")
    
    graph.add_conditional_edges(
        "check_cache",
        route_after_cache_check,
        {
            "gather_info": "gather_info",
            "end": END
        }
    )
    
    graph.add_edge("gather_info", "generate_score")
    graph.add_edge("generate_score", END)

    return graph.compile()

# Create the compiled graph
class_grading_graph = create_class_grading_graph()

if __name__ == "__main__":
    # run with python -m agents.class_grading_agent
    test_messages = [HumanMessage(content="Just lookup the CSE 2331 class at OSU and tell me what you think")]

    # Test the graph
    initial_state = {
        "messages": test_messages,
        "class_name": "CSE 2331",
        "class_score": None,
        "cached": False
    }

    result = class_grading_graph.invoke(initial_state)
    # Print as JSON
    import json
    print(json.dumps(result["class_score"].model_dump(), indent=2))

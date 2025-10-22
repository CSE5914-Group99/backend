from dotenv import load_dotenv
load_dotenv()

from pydantic import BaseModel, Field
from typing import Optional, TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Import tools
from agents.tools.internet_search import basic_tavily_search
#from agents.tools.osu_search import osu_search
#from agents.tools.reddit_search import reddit_search
#from agents.tools.coursicle_search import coursicle_search
#from agents.tools.rate_my_professor import rate_my_professor_search

# TODO
# Implement all tools and import them here and add them to thhe tool list below
# Implement caching of class scores

prompt = '''
You are an expert Ohio State University class difficulty analyzer. Your job is to research and evaluate the difficulty of OSU classes to help students make informed course selection decisions.

## Your Task
Analyze the given class and provide a comprehensive difficulty assessment using multiple metrics. Be objective, evidence-based, and student-focused.

## Research Process
1. **Search for information** about the class using available tools:
   - Course syllabi, descriptions, and requirements
   - Student reviews and experiences (Reddit, RateMyProfessor, Coursicle)
   - Official OSU course catalogs and department resources
   - Discussion forums and student communities

2. **Collect evidence**: Save direct quotes and snippets from your sources that support your scoring decisions

3. **Analyze holistically**: Consider workload, conceptual difficulty, assessment burden, pacing, and student feedback

## Scoring Guidelines

### Overall Score (1-100)
Holistic difficulty score combining all factors:
- 1-20: Very easy, minimal effort
- 21-40: Easy, manageable workload
- 41-60: Moderate, average college course
- 61-80: Challenging, requires significant effort
- 81-100: Extremely difficult, demanding course

### Time Load (0.0-8.0)
How many credit hours does this class FEEL like in terms of weekly time commitment?
- If a 3-credit class feels like 3 hours/week → score ~3.0
- If it feels like 6 hours/week → score ~6.0
- Consider: homework, studying, projects, reading

### Rigor (0-100)
Conceptual and technical depth:
- 0-30: Memorization-based, straightforward concepts
- 31-60: Moderate analytical thinking required
- 61-100: Deep theoretical understanding, complex problem-solving

### Assessment Intensity (0-100)
Frequency and difficulty of exams/quizzes:
- Consider: number of exams, cumulative vs non-cumulative, difficulty level, time pressure
- 0-30: Few, straightforward assessments
- 31-60: Regular exams of moderate difficulty
- 61-100: Frequent, high-stakes, difficult exams

### Project Intensity (0-100)
Complexity and time requirements for projects/assignments:
- 0-30: Light homework, simple assignments
- 31-60: Moderate projects, regular homework
- 61-100: Major projects, extensive coding/writing/research

### Pace (0-100)
Speed of material coverage:
- 0-30: Slow, plenty of review time
- 31-60: Moderate, steady progression
- 61-100: Fast, covers large amounts quickly

### Prerequisites & Co-requisites
List the required and recommended prerequisite/co-requisite courses.

## Evidence Requirements
- **Tags**: Add descriptive tags (e.g., "math-heavy", "project-based", "memorization", "time-consuming", "well-taught")
- **Evidence Snippets**: Include 3-5 direct quotes from student reviews or course materials that justify your scores
- **Confidence**: Rate your confidence (0.0-1.0) based on:
  - 0.0-0.4: Very limited data, mostly guessing
  - 0.5-0.7: Some data available, reasonable estimate
  - 0.8-1.0: Abundant reliable data, high confidence

## Important Notes
- Be objective: Don't inflate or deflate scores based on instructor quality alone
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
    confidence: float = Field(0.6, ge=0.0, le=1.0, description="amount and difficulty of exams")

# Define the state for the graph
class ClassGradingState(TypedDict):
    messages: Annotated[list, add_messages]
    class_name: str
    class_score: ClassScore | None
    cached: bool

# Initialize the ReAct agent with tools
llm = ChatOpenAI(model="gpt-5-mini", temperature=1)
tools = [basic_tavily_search]#, osu_search, reddit_search, coursicle_search, rate_my_professor_search]
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=prompt,
    response_format=ClassScore
)

# Node 1: Check cache for class info
def check_cache(state: ClassGradingState) -> ClassGradingState:
    """Check if class information is already cached"""
    # TODO: Implement actual cache lookup logic
    # For now, always return no cache
    return {
        "cached": False,
        "class_score": None
    }

# Node 2: Score class agent (calls tools)
def score_class_agent(state: ClassGradingState) -> ClassGradingState:
    """Agent that calls various tools to score the class"""
    messages = state["messages"]
    response = agent.invoke({"messages": messages}, debug=False)
    return {
        "messages": response["messages"],
        "class_score": response['structured_response']
    }

# Node 3: Cache class score and relevant course info
def cache_class_score(state: ClassGradingState) -> ClassGradingState:
    """Cache the class scoring information and relevant course info"""
    # TODO: Implement actual caching logic
    # For now, just mark as cached without modifying the class_score
    return {
        "cached": True
    }

# Conditional edge, Route based on cache hit/miss
def route_after_cache_check(state: ClassGradingState) -> Literal["score_class_agent", "end"]:
    """Route to agent if no cache, otherwise end"""
    if state.get("cached") and state.get("class_score"):
        return "end"
    return "score_class_agent"

# Build the graph
def create_class_grading_graph():
    """Create and return the compiled class grading graph"""
    graph = StateGraph(ClassGradingState)

    # Add nodes
    graph.add_node("check_cache", check_cache)
    graph.add_node("score_class_agent", score_class_agent)
    graph.add_node("cache_class_score", cache_class_score)

    # Add edges
    graph.add_edge(START, "check_cache")
    graph.add_conditional_edges(
        "check_cache",
        route_after_cache_check,
        {
            "score_class_agent": "score_class_agent",
            "end": END
        }
    )
    graph.add_edge("score_class_agent", "cache_class_score")
    graph.add_edge("cache_class_score", END)

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

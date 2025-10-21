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

prompt = '''
Hi, you are an example prompt for the class scoring agent. 
please give me the difficulty score for the given class.
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

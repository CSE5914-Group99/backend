from dotenv import load_dotenv
load_dotenv()

from pydantic import BaseModel, Field
from typing import Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Send
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

# Import the class grading agent
from .class_grading_agent import ClassScore, ClassGradingState, class_grading_graph

# Import session factory for creating new sessions in parallel operations
from db.session import get_session_factory

# Import tools
from .tools.internet_search import basic_tavily_search


# Pydantic model for class-teacher tuple
class ClassTeacherTuple(BaseModel):
    class_id: str
    teacher: Optional[str]

    class Config:
        frozen = True  # Make immutable so it can be hashable

    def __hash__(self):
        return hash((self.class_id, self.teacher))

    def __eq__(self, other):
        if not isinstance(other, ClassTeacherTuple):
            return False
        return self.class_id == other.class_id and self.teacher == other.teacher

# Pydantic model for LLM-generated adjusted scores
class ScheduleAnalysis(BaseModel):
    """LLM-generated analysis of schedule difficulty with adjustments"""
    summary: str = Field(description="Overall summary of schedule difficulty considering all factors")
    adjusted_difficulty: int = Field(ge=1, le=100, description="Overall schedule difficulty score adjusted for credit hours, number of classes, and constraints")
    adjusted_assessment_intensity: int = Field(ge=0, le=100, description="Amount and difficulty of exams adjusted for schedule context")
    adjusted_project_intensity: int = Field(ge=0, le=100, description="Amount and difficulty of projects adjusted for schedule context")
    time_load: float = Field(ge=0, le=30, description="Weekly time/effort in hours for this entire schedule")
    adjusted_rigor: int = Field(ge=0, le=100, description="Conceptual/technical depth adjusted for schedule context")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence about schedule score based on data quality")

# Define the ScheduleScore output model
class ScheduleScore(BaseModel):
    """Overall schedule difficulty score and summary"""
    class_scores: dict[ClassTeacherTuple, ClassScore] = Field(description="Map of class ID to individual class scores")
    total_credit_hours: int = Field(description="Total credit hours in the schedule")
    num_classes: int = Field(description="Number of classes in the schedule")
    summary: str = Field(description="overall summary of schedule difficulty")
    adjusted_difficulty: int = Field(ge=1, le=100, description="overall schedule difficulty score adjusted for credit hours and contraints")
    adjusted_assessment_intensity: int = Field(0, ge=0, le=100, description="amount and difficulty of exams adjusted for credit hours and contraints")
    adjusted_project_intensity: int = Field(0, ge=0, le=100, description="amount and difficulty of projects adjusted for credit hours and contraints")
    time_load: float = Field(ge=0, le=30, description="weekly time/effort vibe, how many credit hours it feels like for this entire schedule")
    adjusted_rigor: int = Field(0, ge=0, le=100, description="conceptual/technical depth")
    constraints: str = Field(description="constraints given by user to agent to score schedule (ie. other commitments, time contraints, etc.)")
    confidence: float = Field(0.6, ge=0.0, le=1.0, description="confidence about schedule score (more data online about each class = more sure about assigned score)")

# Prompt for LLM schedule analysis
schedule_analysis_prompt = '''
You are an expert academic advisor analyzing a college student's course schedule at Ohio State University. Your job is to provide a nuanced, holistic assessment of the schedule's difficulty that goes beyond simple averages.

## Your Task
Analyze the given schedule considering:
1. **Individual class difficulties**: Each class has its own difficulty metrics (score, rigor, assessment intensity, project intensity, time load)
2. **Credit hour load**: How many total credit hours? (12-15 is typical, 15-18 is full load, >18 is heavy)
3. **Number of classes**: More classes = more context switching, more deadlines to track
4. **Class interactions**: Do hard classes stack? Are exam schedules likely to overlap?
5. **Time commitment reality**: Does the combined time load create unsustainable weeks?
6. **User constraints**: IMPORTANT - Pay special attention to any user-specified constraints (e.g., part-time job, athletics, family commitments, health conditions). These significantly impact schedule manageability and should heavily influence your difficulty assessment.

## Adjustment Philosophy
- **Don't just average**: A schedule with 5 moderately hard classes can be harder than 3 very hard classes
- **Consider overlap**: Multiple project-heavy classes create crunch times
- **Account for juggling**: 6 classes at 60/100 difficulty each is harder to manage than 4 classes at 75/100
- **Time load realism**: If individual time loads suggest 25+ hours/week, that's unsustainable with other commitments
- **Credit hour context**: 18 credit hours of hard classes is exponentially harder than 12 credit hours of hard classes
- **Factor in constraints**: If user has external commitments (work, sports, etc.), increase difficulty scores accordingly. A 15-hour course load with a 20-hour/week job is effectively like taking 20+ credit hours.

## Scoring Guidelines

### Adjusted Difficulty (1-100)
Consider the compounding effect of:
- High individual class difficulties
- Large number of classes (>5 = significant juggling penalty)
- Heavy credit hour load (>18 = difficulty multiplier)
- Multiple high-rigor classes competing for mental energy

Examples:
- 12 credits, 4 easy classes (avg 35/100) → Adjusted: 30-35
- 15 credits, 5 moderate classes (avg 55/100) → Adjusted: 60-65 (juggling penalty)
- 18 credits, 6 hard classes (avg 70/100) → Adjusted: 80-85 (heavy load + juggling)
- 15 credits, 4 very hard classes (avg 80/100) → Adjusted: 82-87 (less juggling, but intense)

### Time Load (0-30 hours/week)
Estimate realistic weekly hours for THIS SCHEDULE:
- Sum individual time loads
- Add overhead for context switching between classes (+0.5-1 hr per class beyond 4)
- Consider exam weeks (might be unsustainable peaks)
- Be honest: >25 hours/week is very difficult with normal college life

### Adjusted Rigor, Assessment, and Project Intensity (0-100)
Adjust for schedule context:
- Multiple high-rigor classes compete for deep thinking time → increase
- Many assessments across classes create time pressure → increase
- Project deadlines likely to cluster → increase
- Lighter schedules allow more focus → decrease slightly

### Confidence (0.0-1.0)
Average the individual class confidences, then adjust:
- If classes have varying confidence levels, lower overall confidence
- If dealing with many classes, slightly lower confidence (more uncertainty in interactions)

### Summary
Write a 2-4 sentence summary that:
1. Characterizes the overall difficulty (light/manageable/challenging/heavy/overwhelming)
2. Highlights key concerns (e.g., "heavy project load", "many concurrent deadlines", "intense rigor")
3. Mentions the time commitment
4. **If user constraints were provided, explicitly address how they impact schedule manageability**
5. Provides honest guidance about manageability

Be direct and honest. Students need realistic assessments to make good decisions.
'''

# Define the state for the schedule grading graph
class ScheduleGradingState(TypedDict):
    """State for the schedule grading agent"""
    schedule: list[ClassTeacherTuple]  # List of class names and teachers (e.g., ["CSE 2331", "MATH 2568"])
    schedule_score: ScheduleScore | None  # Final schedule score object
    messages: Annotated[list, add_messages]  # Messages for the ReAct agent
    constraints: str | None # User constraints for scoring
    session: AsyncSession | None  # Database session

# Node 3: Score individual class using the class grading graph
async def score_class_agent_graph(state: ClassGradingState) -> dict:
    """
    Execute the class grading graph for a single class.
    This node will be called in parallel for each class in the schedule.
    """
    # Create a new session for this parallel operation to avoid concurrent session errors
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Update state with new session
        state_with_session = {**state, "session": session}
        result = await class_grading_graph.ainvoke(state_with_session)

    class_teacher_tuple = state["class_teacher_tuple"]
    class_score = result["class_score"]

    # Create a partial ScheduleScore with just this one class
    # This will be merged with other parallel results
    # Use ClassTeacherTuple as the key
    partial_schedule_score = ScheduleScore(
        class_scores={class_teacher_tuple: class_score},
        total_credit_hours=0,  # Will be calculated in summarize
        num_classes=0,  # Will be calculated in summarize
        summary="",  # Will be generated by agent in summarize
        adjusted_difficulty=1,  # Will be calculated in summarize (min value is 1)
        adjusted_assessment_intensity=0,  # Will be calculated in summarize
        adjusted_project_intensity=0,  # Will be calculated in summarize
        time_load=0.0,  # Will be calculated in summarize
        adjusted_rigor=0,  # Will be calculated in summarize
        constraints="",  # Will be set in summarize
        confidence=0.0  # Will be calculated in summarize
    )

    # Return the result in a format that can be merged into the schedule state
    return {
        "schedule_score": partial_schedule_score
    }

# Initialize ReAct agent for schedule analysis
llm = ChatOpenAI(model="gpt-5-mini", temperature=1)
tools = [basic_tavily_search]
schedule_analysis_agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=schedule_analysis_prompt,
    response_format=ScheduleAnalysis
)

# Node 4: Summarize schedule and create ScheduleScore object using ReAct agent
async def summarize_schedule(state: ScheduleGradingState) -> ScheduleGradingState:
    """Use ReAct agent to generate nuanced schedule analysis with adjusted difficulty scores"""
    # Get the schedule_score which has been built up with class_scores from parallel executions
    current_schedule_score = state.get("schedule_score")

    if not current_schedule_score or not current_schedule_score.class_scores:
        # No classes to summarize
        return {"schedule_score": None}

    class_scores_dict = current_schedule_score.class_scores
    class_scores_list = list(class_scores_dict.values())

    # Calculate basic metrics
    total_credit_hours = sum(cs.ch for cs in class_scores_list)
    num_classes = len(class_scores_list)

    # Build a summary of each class for the LLM
    class_summaries = []
    for class_teacher_tuple, cs in class_scores_dict.items():
        # Format class display name with teacher if available
        if class_teacher_tuple.teacher:
            class_display = f"{class_teacher_tuple.class_id} (Prof. {class_teacher_tuple.teacher})"
        else:
            class_display = class_teacher_tuple.class_id

        class_summary = (
            f"**{class_display}** ({cs.ch} credits):\n"
            f"  - Difficulty: {cs.score}/100\n"
            f"  - Rigor: {cs.rigor}/100\n"
            f"  - Assessment Intensity: {cs.assessment_intensity}/100\n"
            f"  - Project Intensity: {cs.project_intensity}/100\n"
            f"  - Time Load: {cs.time_load} hrs/week\n"
            f"  - Confidence: {cs.confidence}\n"
            f"  - Summary: {cs.summary}"
        )
        class_summaries.append(class_summary)

    # Prepare prompt for ReAct agent
    classes_info = "\n\n".join(class_summaries)

    # Get user constraints from state
    user_constraints = state.get("constraints", "None specified")

    analysis_request = f"""## Schedule to Analyze

**Total Credit Hours**: {total_credit_hours}
**Number of Classes**: {num_classes}
**User Constraints**: {user_constraints}

### Individual Class Scores:

{classes_info}

Now provide your holistic analysis of this schedule with adjusted difficulty scores. You can use search tools if you need additional context about course interactions or workload patterns.
"""

    # Create message for the agent
    message = HumanMessage(content=analysis_request)

    # Get analysis from ReAct agent
    agent_response = await schedule_analysis_agent.ainvoke({"messages": [message]}, debug=False)
    analysis: ScheduleAnalysis = agent_response['structured_response']

    # Create final ScheduleScore object with agent-generated metrics
    schedule_score = ScheduleScore(
        class_scores=class_scores_dict,
        total_credit_hours=total_credit_hours,
        num_classes=num_classes,
        summary=analysis.summary,
        adjusted_difficulty=analysis.adjusted_difficulty,
        adjusted_assessment_intensity=analysis.adjusted_assessment_intensity,
        adjusted_project_intensity=analysis.adjusted_project_intensity,
        time_load=analysis.time_load,
        adjusted_rigor=analysis.adjusted_rigor,
        constraints=state.get("constraints") or "",
        confidence=analysis.confidence
    )

    return {
        "schedule_score": schedule_score,
        "messages": agent_response["messages"]
    }

# Reducer function to merge schedule scores from parallel executions
def merge_schedule_scores(left: ScheduleScore | None, right: ScheduleScore | None) -> ScheduleScore | None:
    """Merge schedule scores from parallel executions by combining class_scores dicts"""
    if left is None:
        return right
    if right is None:
        return left

    # Merge the class_scores dictionaries from both ScheduleScore objects
    merged_class_scores = {**left.class_scores, **right.class_scores}

    # If either score has non-default summary fields, prefer the one with real data
    # (This happens when summarize_schedule returns a complete score)
    if right.summary and right.summary != "":
        # Right has been summarized - use its summary fields
        return ScheduleScore(
            class_scores=merged_class_scores,
            total_credit_hours=right.total_credit_hours,
            num_classes=right.num_classes,
            summary=right.summary,
            adjusted_difficulty=right.adjusted_difficulty,
            adjusted_assessment_intensity=right.adjusted_assessment_intensity,
            adjusted_project_intensity=right.adjusted_project_intensity,
            time_load=right.time_load,
            adjusted_rigor=right.adjusted_rigor,
            constraints=right.constraints,
            confidence=right.confidence
        )
    elif left.summary and left.summary != "":
        # Left has been summarized - use its summary fields
        return ScheduleScore(
            class_scores=merged_class_scores,
            total_credit_hours=left.total_credit_hours,
            num_classes=left.num_classes,
            summary=left.summary,
            adjusted_difficulty=left.adjusted_difficulty,
            adjusted_assessment_intensity=left.adjusted_assessment_intensity,
            adjusted_project_intensity=left.adjusted_project_intensity,
            time_load=left.time_load,
            adjusted_rigor=left.adjusted_rigor,
            constraints=left.constraints,
            confidence=left.confidence
        )
    else:
        # Neither has been summarized - return default values
        # This happens during parallel class scoring before summarize_schedule runs
        return ScheduleScore(
            class_scores=merged_class_scores,
            total_credit_hours=0,  # Will be calculated in summarize_schedule
            num_classes=0,  # Will be calculated in summarize_schedule
            summary="",  # Will be generated in summarize_schedule
            adjusted_difficulty=1,  # Will be calculated in summarize_schedule (min value is 1)
            adjusted_assessment_intensity=0,  # Will be calculated in summarize_schedule
            adjusted_project_intensity=0,  # Will be calculated in summarize_schedule
            time_load=0.0,  # Will be calculated in summarize_schedule
            adjusted_rigor=0,  # Will be calculated in summarize_schedule
            constraints="",  # Will be set in summarize_schedule
            confidence=0.0  # Will be calculated in summarize_schedule
        )

# Build the schedule grading graph
def create_schedule_grading_graph():
    """Create and return the compiled schedule grading graph"""

    # Create a custom state schema with reducers for schedule_score and messages
    class ScheduleGradingStateWithReducer(TypedDict):
        schedule: list[ClassTeacherTuple]
        schedule_score: Annotated[ScheduleScore | None, merge_schedule_scores]
        messages: Annotated[list, add_messages]
        constraints: str | None
        session: AsyncSession | None

    graph = StateGraph(ScheduleGradingStateWithReducer)

    # Add a simple join node that just passes through
    def join_node(state: ScheduleGradingStateWithReducer):
        """Join node that waits for all parallel tasks to complete"""
        return {}

    # Add nodes
    graph.add_node("score_class_agent_graph", score_class_agent_graph)
    graph.add_node("join", join_node)
    graph.add_node("summarize_schedule", summarize_schedule)

    # Fan out function for parallel scoring
    def fan_out_classes(state: ScheduleGradingStateWithReducer):
        """Fan out to score each class in parallel"""
        schedule = state["schedule"]
        session = state.get("session")

        send_objects = []
        for class_teacher in schedule:
            # Normalize class_id and teacher_name
            class_id = class_teacher.class_id.replace(" ", "").lower()
            teacher_name = class_teacher.teacher.replace(" ", "").lower() if class_teacher.teacher else 'unknown'

            # Create normalized ClassTeacherTuple to use as dictionary key
            normalized_tuple = ClassTeacherTuple(
                class_id=class_id,
                teacher=teacher_name
            )

            # Build message content based on whether teacher is provided
            if teacher_name and teacher_name != 'unknown':
                message_content = f"Evaluate the class {class_id} taught by Professor {class_teacher.teacher}"
            else:
                message_content = f"Evaluate the class {class_id} (no specific instructor provided)"

            send_objects.append(
                Send(
                    "score_class_agent_graph",
                    {
                        "messages": [HumanMessage(content=message_content)],
                        "class_name": class_id,
                        "teacher_name": teacher_name,
                        "class_score": None,
                        "cached": False,
                        "session": session,
                        "class_teacher_tuple": normalized_tuple  # Pass normalized tuple as dict key
                    }
                )
            )

        return send_objects

    # Add edges
    # Fan out from START using Send API for parallel execution
    graph.add_conditional_edges(
        START,
        fan_out_classes
    )

    # After parallel scoring completes, all tasks go to join node
    graph.add_edge("score_class_agent_graph", "join")

    # After join, go to summarize
    graph.add_edge("join", "summarize_schedule")

    # End after summarizing
    graph.add_edge("summarize_schedule", END)

    return graph.compile()

# Create the compiled graph
schedule_grading_graph = create_schedule_grading_graph()

if __name__ == "__main__":
    # run with python -m agents.schedule_grading_agent

    # Test the graph with a sample schedule
    test_schedule = [
        ClassTeacherTuple(class_id="CSE2331", teacher=None),
        ClassTeacherTuple(class_id="PHYSICS 1250", teacher="John Doe")
    ]

    initial_state = {
        "schedule": test_schedule,
        "schedule_score": None,
        "messages": [],
        "session": None  # No session for local testing
    }

    print(f"Scoring schedule: {test_schedule}")
    print("This will score all classes in parallel using the Send API...\n")

    # Run the graph
    result = schedule_grading_graph.invoke(initial_state, debug=False)

    # Print results
    import json
    print("\n=== Schedule Scoring Results ===\n")

    if result.get("schedule_score"):
        schedule_score = result["schedule_score"]
        print("Overall Schedule Summary:")
        print(json.dumps(schedule_score.model_dump(), indent=2))
    else:
        print("No schedule score generated")

    print("\n" + "=" * 80)

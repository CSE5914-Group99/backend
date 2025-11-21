from fastapi import APIRouter, HTTPException
from typing import List

from services.schedule_generator import generate_schedule_options, analyze_generated_schedules
from schemas.schedule import Schedule, GenerateScheduleRequest, GenerateScheduleResponse, AnalyzeSchedulesRequest

router = APIRouter(
    prefix="/generate-schedule",
    tags=["generate-schedule"],
)

@router.post("/", response_model=GenerateScheduleResponse)
async def generate_schedule_endpoint(request: GenerateScheduleRequest):
    try:
        return await generate_schedule_options(request)
    except Exception as e:
        print(f"Error generating schedule: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", response_model=List[Schedule])
async def analyze_schedules_endpoint(request: AnalyzeSchedulesRequest):
    """
    Analyze a list of schedules using the AI agent to calculate difficulty, time load, etc.
    """
    return await analyze_generated_schedules(request)

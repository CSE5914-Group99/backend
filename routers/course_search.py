from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

from services.osu_course_search import (
    CourseSearchError,
    CourseSearchResponse,
    fetch_osu_course_sections,
)


LOGGER = logging.getLogger(__name__)

course_search_router = APIRouter(prefix="/course-search", tags=["course-search"])


@course_search_router.get("", response_model=CourseSearchResponse)
async def search_courses(
    subject: str = Query(..., description="Course subject code or label, e.g. 'CSE'"),
    course_number: str = Query(..., description="Catalog number, e.g. '2231'"),
    term: str = Query("Summer 2025", description="Term text or code shown in PeopleSoft"),
    campus: str = Query("Columbus", description="Campus label or code, e.g. 'Columbus' or 'COL'"),
    open_only: bool = Query(True, description="If false, include closed and waitlisted sections"),
    include_raw_html: bool = Query(
        False,
        description="Set true to return raw PeopleSoft HTML in response for debugging",
    ),
    timeout: float = Query(
        30.0,
        gt=0,
        le=120,
        description="Maximum number of seconds to wait for the PeopleSoft response",
    ),
) -> CourseSearchResponse:
    """Search OSU's public class schedule and return structured section data."""

    try:
        return await fetch_osu_course_sections(
            subject=subject,
            course_number=course_number,
            term=term,
            campus=campus,
            open_only=open_only,
            include_raw_html=include_raw_html,
            timeout=timeout,
        )
    except CourseSearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        LOGGER.exception("PeopleSoft request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to reach OSU PeopleSoft class search",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.exception("Unexpected error during course search")
        raise HTTPException(status_code=500, detail="Unexpected error performing course search") from exc

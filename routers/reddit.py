from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

from agents.tools.reddit_search import search_reddit_threads
from schemas.reddit import RedditSearchResponse


LOGGER = logging.getLogger(__name__)

reddit_router = APIRouter(prefix="/reddit", tags=["reddit"])


@reddit_router.get("/search", response_model=RedditSearchResponse)
async def reddit_search(
    course_number: str = Query(..., description="Course number, e.g. 'CSE 2221'"),
    teacher_name: str = Query(..., description="Instructor name to include in the search"),
    limit_threads: int = Query(5, ge=1, le=30, description="Maximum number of threads to return"),
    comment_limit: int = Query(200, ge=1, le=500, description="Maximum comments fetched per thread"),
) -> RedditSearchResponse:
    """Search the r/OSU subreddit for posts about a course and instructor."""

    try:
        raw_result = await asyncio.to_thread(
            search_reddit_threads,
            course_number,
            teacher_name,
            limit_threads=limit_threads,
            comment_limit=comment_limit,
        )
        return RedditSearchResponse.model_validate(raw_result)
    except RuntimeError as exc:
        LOGGER.warning("Reddit credentials not configured: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        LOGGER.warning(
            "Reddit API returned %s for %s: %s",
            exc.response.status_code,
            exc.request.url,
            exc.response.text,
        )
        detail = (
            f"Reddit API error {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        )
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        LOGGER.exception("Reddit API request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to reach Reddit API") from exc
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.exception("Unexpected error in Reddit search")
        raise HTTPException(status_code=500, detail="Unexpected error during Reddit search") from exc

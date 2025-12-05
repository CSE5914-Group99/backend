from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

from services.rate_my_professor import (
	RateMyProfessorError,
	ProfessorDetail,
	ProfessorSearchResponse,
	OSU_RMP_SCHOOL_ID,
	get_professor_details,
	search_professors,
)


LOGGER = logging.getLogger(__name__)

rate_my_professor_router = APIRouter(prefix="/rate-my-professor", tags=["rate-my-professor"])


@rate_my_professor_router.get("/search", response_model=ProfessorSearchResponse)
async def rate_my_professor_search(
	query: str = Query(..., description="Professor name search query, e.g. 'Stanley Vernier'"),
	school_id: str | None = Query(
		OSU_RMP_SCHOOL_ID,
		description="RateMyProfessors legacy school id to narrow the search (defaults to OSU).",
	),
	first: int = Query(
		8,
		ge=1,
		le=20,
		description="Number of search results to retrieve",
	),
	timeout: float = Query(
		20.0,
		gt=0,
		le=60,
		description="Maximum number of seconds to wait for the RateMyProfessors response",
	),
) -> ProfessorSearchResponse:
	try:
		return await search_professors(
			query=query,
			school_id=school_id,
			first=first,
			timeout=timeout,
		)
	except RateMyProfessorError as exc:
		raise HTTPException(status_code=400, detail=str(exc)) from exc
	except httpx.HTTPError as exc:
		LOGGER.exception("RateMyProfessors request failed: %s", exc)
		raise HTTPException(
			status_code=502,
			detail="Failed to reach RateMyProfessors",
		) from exc


@rate_my_professor_router.get("/professors/{legacy_id}", response_model=ProfessorDetail)
async def rate_my_professor_detail(
	legacy_id: str,
	first: int = Query(
		5,
		ge=1,
		le=15,
		description="Number of recent ratings to include",
	),
	timeout: float = Query(
		20.0,
		gt=0,
		le=60,
		description="Maximum number of seconds to wait for the RateMyProfessors response",
	),
) -> ProfessorDetail:
	try:
		return await get_professor_details(
			legacy_id,
			ratings_first=first,
			timeout=timeout,
		)
	except RateMyProfessorError as exc:
		raise HTTPException(status_code=404, detail=str(exc)) from exc
	except httpx.HTTPError as exc:
		LOGGER.exception("RateMyProfessors request failed: %s", exc)
		raise HTTPException(
			status_code=502,
			detail="Failed to reach RateMyProfessors",
		) from exc


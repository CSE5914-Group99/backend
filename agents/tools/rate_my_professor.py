from __future__ import annotations

import json

from pydantic import BaseModel, Field

from langchain_core.tools import tool

from services.rate_my_professor import (
	OSU_RMP_SCHOOL_ID,
	RateMyProfessorError,
	get_professor_details,
	search_professors,
)


class RateMyProfessorInput(BaseModel):
	"""Input schema for the RateMyProfessor tool."""

	query: str | None = Field(
		default=None,
		description="Professor name search query. Required when professor_id not provided.",
	)
	professor_id: str | None = Field(
		default=None,
		description="Legacy professor id (as shown in the RateMyProfessors URL). When provided, returns detailed info.",
	)
	school_id: str | None = Field(
		default=OSU_RMP_SCHOOL_ID,
		description="RateMyProfessor school id to constrain search results (defaults to OSU).",
	)
	first: int | None = Field(
		default=8,
		ge=1,
		le=20,
		description="Number of search results or ratings to fetch (capped to keep payload small).",
	)


@tool("rate_my_professor", args_schema=RateMyProfessorInput)
async def rate_my_professor_tool(
	query: str | None = None,
	professor_id: str | None = None,
	school_id: str | None = OSU_RMP_SCHOOL_ID,
	first: int | None = 8,
) -> str:
	"""Fetch RateMyProfessors search results or professor details."""

	first = first or 8

	try:
		if professor_id:
			detail = await get_professor_details(professor_id, ratings_first=first)
			return json.dumps(detail.model_dump(), ensure_ascii=False, indent=2)

		if not query:
			raise ValueError("Either professor_id or query must be supplied")

		search_response = await search_professors(
			query=query,
			school_id=school_id,
			first=first,
		)
		return json.dumps(search_response.model_dump(), ensure_ascii=False, indent=2)

	except RateMyProfessorError as exc:
		return json.dumps({"error": str(exc)}, ensure_ascii=False)


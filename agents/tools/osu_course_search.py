"""LangChain-compatible tool for searching OSU course sections via PeopleSoft."""

from __future__ import annotations

import json
from pydantic import BaseModel, Field

from langchain_core.tools import tool

from services.osu_course_search import fetch_osu_course_sections


class OSUCourseSearchInput(BaseModel):
    """Input schema for the OSU course search tool."""

    subject: str = Field(..., description="Course subject code or label, e.g. 'CSE'")
    course_number: str = Field(..., description="Catalog number, e.g. '2231'")
    term: str = Field(
        default="Summer 2025",
        description="Term text or code as displayed in PeopleSoft (e.g. 'Summer 2025' or '1254')",
    )
    campus: str = Field(
        default="Columbus",
        description="Campus label or PeopleSoft campus code (e.g. 'Columbus' or 'COL')",
    )
    open_only: bool = Field(
        default=True,
        description="Set to False to include closed and waitlisted sections in the results",
    )


@tool("osu_course_search", args_schema=OSUCourseSearchInput)
async def osu_course_search_tool(
    subject: str,
    course_number: str,
    term: str = "Summer 2025",
    campus: str = "Columbus",
    open_only: bool = True,
) -> str:
    """Fetch live section availability for an OSU course via the public class search."""

    result = await fetch_osu_course_sections(
        subject=subject,
        course_number=course_number,
        term=term,
        campus=campus,
        open_only=open_only,
    )

    return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)

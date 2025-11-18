"""Utilities for querying RateMyProfessors using the public search pages."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterable

import httpx
from pydantic import BaseModel, Field


LOGGER = logging.getLogger(__name__)

OSU_RMP_SCHOOL_ID = "724"

DEFAULT_HEADERS = {
	"User-Agent": (
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
		"(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
	),
	"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	"Referer": "https://www.ratemyprofessors.com/",
}


class RateMyProfessorError(RuntimeError):
	"""Raised when scraping RateMyProfessors fails."""


class ProfessorSearchResult(BaseModel):
	id: str | None = None
	legacy_id: int | None = Field(default=None)
	first_name: str | None = None
	last_name: str | None = None
	department: str | None = None
	school_id: str | None = None
	school_name: str | None = None
	school_city: str | None = None
	school_state: str | None = None
	avg_rating: float | None = None
	num_ratings: int | None = None
	rating_class: str | None = None
	would_take_again_percent: float | None = None
	difficulty_rating: float | None = None
	course_codes: list[str] = Field(default_factory=list)


class ProfessorRatingSnippet(BaseModel):
	comment: str | None = None
	class_name: str | None = Field(default=None)
	date: str | None = None
	overall_rating: float | None = None
	difficulty_rating: float | None = None
	helpful_rating: float | None = None
	clarity_rating: float | None = None
	would_take_again: str | None = None
	grade: str | None = None
	attendance_mandatory: str | None = None
	rating_tags: list[str] | None = None


class ProfessorDetail(BaseModel):
	legacy_id: int | None = None
	first_name: str | None = None
	last_name: str | None = None
	department: str | None = None
	school_name: str | None = None
	school_city: str | None = None
	school_state: str | None = None
	avg_rating: float | None = None
	num_ratings: int | None = None
	would_take_again_percent: float | None = None
	difficulty_rating: float | None = None
	rating_class: str | None = None
	recent_ratings: list[ProfessorRatingSnippet] = Field(default_factory=list)


class ProfessorSearchResponse(BaseModel):
	query: str
	school_id: str | None = None
	results: list[ProfessorSearchResult] = Field(default_factory=list)
	has_next_page: bool = False


_STATE_MARKERS = (
	"window.__RELAY_STORE__",
	"window.__PRELOADED_STATE__",
)


def _extract_json_block(html: str, marker: str) -> dict[str, Any] | None:
	marker_index = html.find(marker)
	if marker_index == -1:
		return None

	assignment_index = html.find("=", marker_index)
	if assignment_index == -1:
		return None

	start = html.find("{", assignment_index)
	if start == -1:
		return None

	depth = 0
	in_string = False
	escape_next = False

	for idx in range(start, len(html)):
		char = html[idx]

		if in_string:
			if escape_next:
				escape_next = False
			elif char == "\\":
				escape_next = True
			elif char == '"':
				in_string = False
			continue

		if char == '"':
			in_string = True
		elif char == "{":
			depth += 1
		elif char == "}":
			depth -= 1
			if depth == 0:
				json_blob = html[start : idx + 1]
				try:
					return json.loads(json_blob)
				except json.JSONDecodeError as exc:
					raise RateMyProfessorError("Failed to parse RateMyProfessors state payload") from exc

	return None


def _extract_state(html: str) -> dict[str, Any]:
	for marker in _STATE_MARKERS:
		state = _extract_json_block(html, marker)
		if state is not None:
			return state
	raise RateMyProfessorError("Unable to locate data store in RateMyProfessors response")


def _gather_teacher_nodes(state: Any) -> list[dict[str, Any]]:
	results: list[dict[str, Any]] = []
	visited: set[int] = set()

	def walk(value: Any) -> None:
		if isinstance(value, dict):
			marker = id(value)
			if marker in visited:
				return
			visited.add(marker)
			keys = set(value.keys())
			if {"firstName", "lastName", "avgRating"}.issubset(keys) and "legacyId" in keys:
				results.append(value)
			else:
				for nested in value.values():
					walk(nested)
		elif isinstance(value, list):
			for item in value:
				walk(item)

	walk(state)
	return results


def _resolve_school(state: Any, school_value: Any) -> dict[str, Any]:
	if not isinstance(school_value, dict):
		return {}
	if "__ref" in school_value and isinstance(state, dict):
		ref_key = school_value.get("__ref")
		if isinstance(ref_key, str):
			return state.get(ref_key, {}) or {}
	return school_value


def _coerce_float(value: Any) -> float | None:
	try:
		return float(value) if value is not None else None
	except (TypeError, ValueError):
		return None


def _coerce_int(value: Any) -> int | None:
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


async def search_professors(
	query: str,
	*,
	school_id: str | None = OSU_RMP_SCHOOL_ID,
	first: int = 8,
	timeout: float = 20.0,
) -> ProfessorSearchResponse:
	school_segment = school_id or OSU_RMP_SCHOOL_ID
	url = f"https://www.ratemyprofessors.com/search/professors/{school_segment}"
	params = {"q": query, "page": 1}

	async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
		response = await client.get(url, params=params)
		response.raise_for_status()
		state = _extract_state(response.text)

	teachers = _gather_teacher_nodes(state)
	def score_teacher(node: dict[str, Any]) -> int:
		# Higher score signals richer payload — prefer entries that include nested school data.
		score = 0
		for key in ("department", "avgRating", "school"):
			value = node.get(key)
			if value:
				score += 1
		if isinstance(node.get("school"), dict):
			score += 2
		return score

	unique: dict[int, dict[str, Any]] = {}
	for teacher in teachers:
		legacy_id = _coerce_int(teacher.get("legacyId"))
		if legacy_id is None:
			continue
		existing = unique.get(legacy_id)
		if existing is None or score_teacher(teacher) > score_teacher(existing):
			unique[legacy_id] = teacher

	sorted_teachers = list(unique.values())[:first]

	results: list[ProfessorSearchResult] = []
	for teacher in sorted_teachers:
		school_data = _resolve_school(state, teacher.get("school"))
		codes_value = teacher.get("courseCodes")
		course_entries: Iterable[dict[str, Any]] = []
		if isinstance(codes_value, dict) and isinstance(state, dict) and "__refs" in codes_value:
			refs = codes_value.get("__refs")
			if isinstance(refs, list):
				course_entries = [state.get(str(ref), {}) for ref in refs]
		elif isinstance(codes_value, list):
			course_entries = codes_value

		result = ProfessorSearchResult(
			id=str(teacher.get("legacyId")) if teacher.get("legacyId") is not None else None,
			legacy_id=_coerce_int(teacher.get("legacyId")),
			first_name=teacher.get("firstName"),
			last_name=teacher.get("lastName"),
			department=teacher.get("department"),
			school_id=str(school_data.get("legacyId")) if school_data.get("legacyId") else None,
			school_name=school_data.get("name"),
			school_city=school_data.get("city"),
			school_state=school_data.get("state"),
			avg_rating=_coerce_float(teacher.get("avgRating")),
			num_ratings=_coerce_int(teacher.get("numRatings")),
			rating_class=teacher.get("ratingClass"),
			would_take_again_percent=_coerce_float(teacher.get("wouldTakeAgainPercent")),
			difficulty_rating=_coerce_float(
				teacher.get("difficultyRating") or teacher.get("avgDifficulty")
			),
			course_codes=[
				f"{course.get('courseCode')} - {course.get('courseName')}"
				for course in course_entries
				if isinstance(course, dict)
			],
		)
		results.append(result)

	return ProfessorSearchResponse(
		query=query,
		school_id=school_id,
		results=results,
		has_next_page=False,
	)


def _gather_ratings(state: Any, legacy_id: int, limit: int) -> list[ProfessorRatingSnippet]:
	collected: dict[int, dict[str, Any]] = {}
	visited: set[int] = set()

	def walk(value: Any) -> None:
		if isinstance(value, dict):
			marker = id(value)
			if marker in visited:
				return
			visited.add(marker)
			if value.get("__typename") == "Rating" and "comment" in value:
				legacy = _coerce_int(value.get("legacyId"))
				if legacy is not None and legacy not in collected:
					collected[legacy] = value
			for nested in value.values():
				walk(nested)
		elif isinstance(value, list):
			for item in value:
				walk(item)

	walk(state)

	def rating_score(item: dict[str, Any]) -> tuple[Any, ...]:
		date = item.get("date") or ""
		return (date,)

	sorted_entries = sorted(collected.values(), key=rating_score, reverse=True)
	trimmed = sorted_entries[:limit]

	def normalize_would_take_again(raw: Any) -> str | None:
		if raw in (None, "", -1):
			return None
		if raw in (1, "1", "Y", "y", True):
			return "Yes"
		if raw in (0, "0", "N", "n", False):
			return "No"
		return str(raw)

	def normalize_tags(raw: Any) -> list[str] | None:
		if raw is None:
			return None
		if isinstance(raw, list):
			return [str(tag) for tag in raw if tag]
		if isinstance(raw, str):
			parts = [segment.strip() for segment in raw.split("--")]
			return [part for part in parts if part]
		return None

	results: list[ProfessorRatingSnippet] = []
	for entry in trimmed:
		helpful = _coerce_float(entry.get("helpfulRating"))
		clarity = _coerce_float(entry.get("clarityRating"))
		overall = _coerce_float(entry.get("overallRating"))
		if overall is None:
			scores = [score for score in (helpful, clarity) if score is not None]
			if scores:
				overall = sum(scores) / len(scores)

		difficulty = _coerce_float(entry.get("difficultyRating"))
		results.append(
			ProfessorRatingSnippet(
				comment=entry.get("comment"),
				class_name=entry.get("class"),
				date=entry.get("date"),
				overall_rating=overall,
				difficulty_rating=difficulty,
				helpful_rating=helpful,
				clarity_rating=clarity,
				would_take_again=normalize_would_take_again(entry.get("wouldTakeAgain")),
				grade=entry.get("grade"),
				attendance_mandatory=entry.get("attendanceMandatory"),
				rating_tags=normalize_tags(entry.get("ratingTags")),
			),
		)

	return results


async def get_professor_details(
	legacy_id: str,
	*,
	ratings_first: int = 5,
	timeout: float = 20.0,
) -> ProfessorDetail:
	legacy_int = _coerce_int(legacy_id)
	if legacy_int is None:
		raise RateMyProfessorError("Professor legacy id must be an integer")

	url = f"https://www.ratemyprofessors.com/professor/{legacy_int}"

	async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
		response = await client.get(url)
		if response.status_code == 404:
			raise RateMyProfessorError("Professor not found")
		response.raise_for_status()
		state = _extract_state(response.text)

	teachers = _gather_teacher_nodes(state)
	teacher = next((t for t in teachers if _coerce_int(t.get("legacyId")) == legacy_int), None)
	if teacher is None:
		raise RateMyProfessorError("Professor not found in response payload")

	ratings = _gather_ratings(state, legacy_int, ratings_first)
	school = _resolve_school(state, teacher.get("school"))

	return ProfessorDetail(
		legacy_id=legacy_int,
		first_name=teacher.get("firstName"),
		last_name=teacher.get("lastName"),
		department=teacher.get("department"),
		school_name=school.get("name"),
		school_city=school.get("city"),
		school_state=school.get("state"),
		avg_rating=_coerce_float(teacher.get("avgRating")),
		num_ratings=_coerce_int(teacher.get("numRatings")),
		would_take_again_percent=_coerce_float(teacher.get("wouldTakeAgainPercent")),
		difficulty_rating=_coerce_float(
			teacher.get("difficultyRating") or teacher.get("avgDifficulty")
		),
		rating_class=teacher.get("ratingClass"),
		recent_ratings=ratings,
	)


def search_professors_sync(*args, **kwargs) -> ProfessorSearchResponse:
	return asyncio.run(search_professors(*args, **kwargs))


def get_professor_details_sync(*args, **kwargs) -> ProfessorDetail:
	return asyncio.run(get_professor_details(*args, **kwargs))


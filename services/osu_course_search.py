"""Utilities for scraping OSU's public PeopleSoft class search."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from dataclasses import dataclass
from typing import Mapping, MutableMapping

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field


LOGGER = logging.getLogger(__name__)

PEOPLESOFT_BASE_URL = (
    "https://courses.erppub.osu.edu/psc/ps/EMPLOYEE/PUB/c/COMMUNITY_ACCESS.CLASS_SEARCH.GBL"
)

# Default headers mimic a recent Chromium browser to avoid simple bot blocks.
DEFAULT_HEADERS: Mapping[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Origin": "https://courses.erppub.osu.edu",
    "Referer": PEOPLESOFT_BASE_URL,
}


class CourseSearchError(RuntimeError):
    """Raised when the PeopleSoft search flow fails."""


class CourseSection(BaseModel):
    """Structured representation of an individual course section."""

    id: str | None = None
    title: str | None = Field(None, description="Course title shown in the results group header")
    courseId: str | None = Field(None, description="Course ID, e.g. 'CSE 2231'")
    instructor: str | None = Field(None, description="Primary instructor name")
    startTime: str | None = Field(None, description="Start time in HH:mm (24h) format")
    endTime: str | None = Field(None, description="End time in HH:mm (24h) format")
    type: str | None = Field(None, description="Component type e.g. Lecture, Lab")
    difficultyRating: float | None = None
    mode: str | None = Field(None, description="Instruction mode e.g. In-person, Online")
    session: int | None = Field(None, description="PeopleSoft class number (unique ID)")
    status: str | None = Field(None, description="Enrollment status derived from icon alt text")
    repeatDays: list[str] | None = Field(None, description="List of days, e.g. ['Monday', 'Wednesday']")
    campus: str | None = None
    semester: str | None = None


class CourseSearchResponse(BaseModel):
    """Top-level response for a course search invocation."""

    subject: str = Field(..., description="Course subject provided by the caller")
    course_number: str = Field(..., description="Catalog number provided by the caller")
    term: str = Field(..., description="Term text or code used for the search")
    campus: str = Field(..., description="Campus text or code used for the search")
    open_only: bool = Field(True, description="Whether only open classes were requested")
    sections: list[CourseSection] = Field(default_factory=list)
    result_count: int = Field(0, description="Number of sections parsed from the response")
    raw_html: str | None = Field(
        None,
        description=(
            "Raw PeopleSoft HTML, useful when debugging. Omitted when include_raw_html=False."
        ),
    )


@dataclass(frozen=True)
class _FormArtifacts:
    """Helper container for form metadata scraped from the page."""

    term_select: Tag
    subject_select: Tag
    course_number_input: Tag
    campus_select: Tag
    open_only_checkbox: Tag | None
    institution_select: Tag | None
    search_button: Tag


def _extract_hidden_fields(soup: BeautifulSoup) -> dict[str, str]:
    return {
        element["name"]: element.get("value", "")
        for element in soup.select("input[type='hidden'][name]")
    }


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value.strip()) or None


def _extract_form_artifacts(soup: BeautifulSoup) -> _FormArtifacts:
    """Gather key controls from the search form."""

    term_select = soup.select_one("select[name*='STRM']")
    subject_select = soup.select_one("select[name*='SUBJECT']")
    course_number_input = soup.select_one("input[name*='CATALOG_NBR']")
    campus_select = soup.select_one("select[name*='CAMPUS']")
    open_only_checkbox = soup.select_one("input[type='checkbox'][name*='SSR_OPEN_ONLY']")
    institution_select = soup.select_one("select[name*='INSTITUTION']")
    search_button = soup.select_one("input[name*='SSR_PB_CLASS_SRCH']")

    if not all([term_select, subject_select, course_number_input, campus_select, search_button]):
        raise CourseSearchError("Unable to locate expected search form controls on PeopleSoft page")

    return _FormArtifacts(
        term_select=term_select,
        subject_select=subject_select,
        course_number_input=course_number_input,
        campus_select=campus_select,
        open_only_checkbox=open_only_checkbox,
        institution_select=institution_select,
        search_button=search_button,
    )


def _resolve_select_value(select: Tag, requested: str | None, field_label: str) -> str:
    if requested is None:
        # Leave whatever value PeopleSoft defaults to
        current_value = select.get("value")
        if current_value:
            return current_value

    requested_normalized = (requested or "").strip().lower()
    for option in select.find_all("option"):
        option_value = option.get("value", "").strip()
        option_text = option.get_text(strip=True)
        if requested_normalized in {option_value.lower(), option_text.lower()}:
            return option_value

    raise CourseSearchError(
        f"Could not resolve value '{requested}' for {field_label}; available options: "
        + ", ".join(option.get_text(strip=True) for option in select.find_all("option"))
    )

def _update_checkbox_payload(
    payload: MutableMapping[str, str], checkbox: Tag | None, flag: bool
) -> None:
    if checkbox is None:
        return

    checkbox_name = checkbox.get("name")
    if not checkbox_name:
        return

    value = "Y" if flag else "N"
    payload[checkbox_name] = value

    if "$chk$" in checkbox_name:
        base_name = checkbox_name.split("$chk$", 1)[0]
        payload[base_name] = value
    else:
        payload[checkbox_name] = value


def _parse_sections(soup: BeautifulSoup, subject: str, course_number: str, campus: str, semester: str) -> list[CourseSection]:
    sections: list[CourseSection] = []
    course_group_selector = "div[id^='win0divSSR_CLSRSLT_WRK_GROUPBOX2$']"

    for group in soup.select(course_group_selector):
        title_element = group.select_one("div[id^='win0divSSR_CLSRSLT_WRK_GROUPBOX2GP']")
        course_title = _clean_text(title_element.get_text(" ", strip=True)) if title_element else None

        for section_block in group.select("div[id^='win0divSSR_CLSRSLT_WRK_GROUPBOX3$']"):
            class_number_str = _clean_text(
                getattr(section_block.select_one("span[id^='MTG_CLASS_NBR']"), "get_text", lambda **_: "")(
                    strip=True
                )
            )
            session_id = None
            if class_number_str and class_number_str.isdigit():
                session_id = int(class_number_str)

            section_text = _clean_text(
                getattr(section_block.select_one("span[id^='MTG_CLASSNAME']"), "get_text", lambda **_: "")(
                    strip=True
                )
            )
            days_times = _clean_text(
                getattr(section_block.select_one("span[id^='MTG_DAYTIME']"), "get_text", lambda **_: "")(
                    strip=True
                )
            )
            room = _clean_text(
                getattr(section_block.select_one("span[id^='MTG_ROOM']"), "get_text", lambda **_: "")(
                    strip=True
                )
            )
            instructor = _clean_text(
                getattr(section_block.select_one("span[id^='MTG_INSTR']"), "get_text", lambda **_: "")(
                    strip=True
                )
            )
            meeting_dates = _clean_text(
                getattr(section_block.select_one("span[id^='MTG_TOPIC']"), "get_text", lambda **_: "")(
                    strip=True
                )
            )

            status_icon = section_block.select_one(
                "div[id^='win0divDERIVED_CLSRCH_SSR_STATUS_LONG'] img"
            )
            status = _clean_text(status_icon.get("alt")) if status_icon else None

            # notes_block = section_block.select_one("div[id^='win0divDERIVED_CLSRCH_DESCRLONG']")
            # if not notes_block:
            #     notes_block = section_block.find_next(
            #         "div", id=re.compile(r"DERIVED_CLSRCH_DESCRLONG")
            #     )
            # notes = _clean_text(notes_block.get_text(strip=True)) if notes_block else None
            # if notes and notes.startswith("Notes:"):
            #     notes = notes[6:].strip()

            start_time, end_time, repeat_days = _parse_meeting_time(days_times)

            # Filter out empty rows that are used for layout padding
            if not any([class_number_str, section_text, days_times, room, instructor, meeting_dates]):
                continue

            # Determine type
            course_type = "Lecture"
            if section_text:
                if "LAB" in section_text:
                    course_type = "Lab"
                elif "REC" in section_text:
                    course_type = "Recitation"
                elif "SEM" in section_text:
                    course_type = "Seminar"
            
            # Determine mode
            mode = "In-person"
            if room and ("online" in room.lower() or "web" in room.lower()):
                mode = "Online"

            sections.append(
                CourseSection(
                    courseId=f"{subject} {course_number}",
                    title=course_title,
                    session=session_id,
                    instructor=instructor,
                    startTime=start_time,
                    endTime=end_time,
                    repeatDays=repeat_days,
                    type=course_type,
                    mode=mode,
                    status=status,
                    campus=campus,
                    semester=semester
                )
            )

    return sections


def _get_element_action_id(element: Tag | None) -> str:
    if element is None:
        raise CourseSearchError("Expected form control missing action identifier")
    action_id = element.get("id") or element.get("name")
    if not action_id:
        raise CourseSearchError("Unable to determine PeopleSoft action identifier for control")
    return action_id


async def _submit_form_action(
    client: httpx.AsyncClient,
    hidden_fields: Mapping[str, str],
    artifacts: _FormArtifacts,
    *,
    updates: Mapping[str, str],
    action: str,
    open_only_flag: bool | None = None,
) -> tuple[BeautifulSoup, dict[str, str], _FormArtifacts | None]:
    payload: dict[str, str] = dict(hidden_fields)
    payload.update(updates)
    payload["ICAction"] = action
    payload.setdefault("ICResubmit", hidden_fields.get("ICResubmit", "0"))
    payload.setdefault("ICChanged", hidden_fields.get("ICChanged", "0"))

    if open_only_flag is not None:
        _update_checkbox_payload(payload, artifacts.open_only_checkbox, open_only_flag)

    response = await client.post(
        PEOPLESOFT_BASE_URL,
        data=payload,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    hidden_fields = _extract_hidden_fields(soup)

    try:
        artifacts = _extract_form_artifacts(soup)
    except CourseSearchError:
        artifacts = None

    return soup, hidden_fields, artifacts


async def fetch_osu_course_sections(
    subject: str,
    course_number: str,
    *,
    term: str = "Summer 2025",
    campus: str = "Columbus",
    open_only: bool = True,
    include_raw_html: bool = False,
    timeout: float = 30.0,
) -> CourseSearchResponse:
    """Scrape OSU's public class search for the given subject & catalog number."""

    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        initial_response = await client.get(PEOPLESOFT_BASE_URL)
        initial_response.raise_for_status()

        soup = BeautifulSoup(initial_response.text, "lxml")
        hidden_fields = _extract_hidden_fields(soup)
        artifacts = _extract_form_artifacts(soup)

        term_value = _resolve_select_value(artifacts.term_select, term, "term")
        institution_value = None
        if artifacts.institution_select is not None:
            institution_value = _resolve_select_value(
                artifacts.institution_select, None, "institution"
            )

        # Step 1: select term to match UI flow.
        updates = {artifacts.term_select.get("name"): term_value}
        if institution_value is not None:
            updates[artifacts.institution_select.get("name")] = institution_value

        soup, hidden_fields, artifacts = await _submit_form_action(
            client,
            hidden_fields,
            artifacts,
            updates=updates,
            action=_get_element_action_id(artifacts.term_select),
        )

        if artifacts is None:
            raise CourseSearchError("Unexpected response while selecting academic term")

        term_value = _resolve_select_value(artifacts.term_select, term, "term")
        campus_value = _resolve_select_value(artifacts.campus_select, campus, "campus")
        if artifacts.institution_select is not None:
            institution_value = _resolve_select_value(
                artifacts.institution_select, None, "institution"
            )

        # Step 2: select campus (persists term as well).
        updates = {
            artifacts.term_select.get("name"): term_value,
            artifacts.campus_select.get("name"): campus_value,
        }
        if institution_value is not None:
            updates[artifacts.institution_select.get("name")] = institution_value

        soup, hidden_fields, artifacts = await _submit_form_action(
            client,
            hidden_fields,
            artifacts,
            updates=updates,
            action=_get_element_action_id(artifacts.campus_select),
        )

        if artifacts is None:
            raise CourseSearchError("Unexpected response while selecting campus")

        term_value = _resolve_select_value(artifacts.term_select, term, "term")
        campus_value = _resolve_select_value(artifacts.campus_select, campus, "campus")
        subject_value = _resolve_select_value(artifacts.subject_select, subject, "subject")
        if artifacts.institution_select is not None:
            institution_value = _resolve_select_value(
                artifacts.institution_select, None, "institution"
            )

        # Step 3: execute search with all criteria.
        updates = {
            artifacts.term_select.get("name"): term_value,
            artifacts.subject_select.get("name"): subject_value,
            artifacts.campus_select.get("name"): campus_value,
            artifacts.course_number_input.get("name"): course_number.strip(),
        }
        if institution_value is not None:
            updates[artifacts.institution_select.get("name")] = institution_value

        soup, hidden_fields, _ = await _submit_form_action(
            client,
            hidden_fields,
            artifacts,
            updates=updates,
            action=_get_element_action_id(artifacts.search_button),
            open_only_flag=open_only,
        )

        result_html = str(soup)
        result_soup = soup

        no_result_banner = result_soup.find(id="DERIVED_CLSRCH_SSR_MSG_TEXT")
        if no_result_banner:
            banner_text = no_result_banner.get_text(strip=True).lower()
            if "no classes found" in banner_text:
                return CourseSearchResponse(
                    subject=subject,
                    course_number=course_number,
                    term=term,
                    campus=campus,
                    open_only=open_only,
                    sections=[],
                    result_count=0,
                    raw_html=result_html if include_raw_html else None,
                )

        sections = _parse_sections(result_soup, subject, course_number, campus, term)

        return CourseSearchResponse(
            subject=subject,
            course_number=course_number,
            term=term,
            campus=campus,
            open_only=open_only,
            sections=sections,
            result_count=len(sections),
            raw_html=result_html if include_raw_html else None,
        )


def fetch_osu_course_sections_sync(*args, **kwargs) -> CourseSearchResponse:
    """Synchronous convenience wrapper for non-async contexts."""

    return asyncio.run(fetch_osu_course_sections(*args, **kwargs))

def _parse_meeting_time(days_times: str | None) -> tuple[str | None, str | None, list[str] | None]:
    if not days_times or days_times == "TBA":
        return None, None, None
    
    match = re.search(r'(\d{1,2}:\d{2}(?:[AP]M)?)\s*-\s*(\d{1,2}:\d{2}(?:[AP]M)?)', days_times, re.IGNORECASE)
    if not match:
        return None, None, None

    start_str = match.group(1)
    end_str = match.group(2)
    
    days_part = days_times[:match.start()].strip()
    days_map = {
        "Mo": "Monday", "Tu": "Tuesday", "We": "Wednesday", 
        "Th": "Thursday", "Fr": "Friday", "Sa": "Saturday", "Su": "Sunday"
    }
    days = []
    i = 0
    while i < len(days_part):
        chunk = days_part[i:i+2]
        if chunk in days_map:
            days.append(days_map[chunk])
            i += 2
        else:
            i += 1
            
    def normalize_time(t_str):
        t_str = t_str.upper()
        try:
            dt = datetime.strptime(t_str, "%I:%M%p")
            return dt
        except ValueError:
            pass
        try:
            dt = datetime.strptime(t_str, "%H:%M")
            if dt.hour < 7:
                dt = dt.replace(hour=dt.hour + 12)
            return dt
        except ValueError:
            return None

    s_dt = normalize_time(start_str)
    e_dt = normalize_time(end_str)
    
    if s_dt and e_dt:
        if e_dt < s_dt:
             e_dt = e_dt.replace(hour=e_dt.hour + 12)
        return s_dt.strftime("%H:%M"), e_dt.strftime("%H:%M"), days
        
    return None, None, days

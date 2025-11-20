"""Utilities for searching r/OSU threads and collecting comments via Reddit API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit, urlunsplit

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


_MODULE_DIR = Path(__file__).resolve().parents[2]
_BACKEND_ENV = _MODULE_DIR / ".env"
if _BACKEND_ENV.exists():
    load_dotenv(_BACKEND_ENV)
load_dotenv()  # Fallback to current working directory if needed

CLIENT_ID = os.getenv("REDDIT_USER_SCRIPT")
CLIENT_SECRET = os.getenv("REDDIT_SECRET")
READONLY_SCOPES = "read"

REDDIT_BASE_URL = "https://www.reddit.com"
REDDIT_OAUTH_URL = "https://oauth.reddit.com"
TOKEN_ENDPOINT = f"{REDDIT_BASE_URL}/api/v1/access_token"
SUBREDDIT = "OSU"
DEFAULT_USER_AGENT = "G99CourseBot/0.1 (by u/unknown)"

_cached_token: str | None = None
_token_expiry: float = 0.0


def _extract_comments(children: List[Dict[str, Any]], depth: int = 0) -> List[Dict[str, Any]]:
    """Recursively extract comment payloads from Reddit JSON response."""
    comments: List[Dict[str, Any]] = []
    for child in children:
        kind = child.get("kind")
        data = child.get("data", {})
        if kind != "t1":
            continue

        replies = data.get("replies")
        nested_children: List[Dict[str, Any]] = []
        if isinstance(replies, dict):
            nested_children = replies.get("data", {}).get("children", [])

        comment = {
            "id": data.get("id"),
            "author": data.get("author"),
            "body": data.get("body"),
            "score": data.get("score"),
            "created_utc": data.get("created_utc"),
            "permalink": data.get("permalink"),
            "depth": depth,
            "replies": _extract_comments(nested_children, depth=depth + 1) if nested_children else [],
        }
        comments.append(comment)

    return comments


def _normalize_permalink(permalink: str | None) -> str | None:
    if not permalink:
        return None
    split = urlsplit(permalink)
    if split.scheme:
        return permalink
    return urlunsplit(("https", "www.reddit.com", split.path, split.query, split.fragment))


def _get_oauth_token(client: httpx.Client) -> str:
    global _cached_token, _token_expiry
    now = time.time()
    if _cached_token and now < _token_expiry - 30:
        return _cached_token

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("Missing Reddit API credentials in environment variables")

    auth = (CLIENT_ID, CLIENT_SECRET)
    data = {"grant_type": "client_credentials", "scope": READONLY_SCOPES}
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    resp = client.post(TOKEN_ENDPOINT, data=data, auth=auth, headers=headers)
    resp.raise_for_status()
    payload = resp.json()
    _cached_token = payload.get("access_token")
    expires_in = payload.get("expires_in", 3600)
    _token_expiry = now + float(expires_in)
    if not _cached_token:
        raise RuntimeError("Unable to obtain Reddit access token")
    return _cached_token


def search_reddit_threads(
    course_number: str,
    teacher_name: str,
    *,
    limit_threads: int = 5,
    comment_limit: int = 200,
    session: httpx.Client | None = None,
) -> Dict[str, Any]:
    """Search r/OSU for threads mentioning the course and instructor and collect comments."""

    query = f"\"{course_number}\" \"{teacher_name}\""
    close_session = False
    client = session
    if client is None:
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        client = httpx.Client(headers=headers, timeout=20.0)
        close_session = True

    try:
        token = _get_oauth_token(client)
        oauth_headers = {"Authorization": f"bearer {token}", "User-Agent": DEFAULT_USER_AGENT}

        params = {
            "q": query,
            "restrict_sr": "on",
            "sort": "relevance",
            "limit": str(limit_threads),
            "t": "all",
            "type": "link",
        }
        search_resp = client.get(
            f"{REDDIT_OAUTH_URL}/r/{SUBREDDIT}/search",
            params=params,
            headers=oauth_headers,
        )
        search_resp.raise_for_status()
        payload = search_resp.json()
        posts = payload.get("data", {}).get("children", [])

        threads: List[Dict[str, Any]] = []
        for post in posts:
            if post.get("kind") != "t3":
                continue

            post_data = post.get("data", {})
            permalink = _normalize_permalink(post_data.get("permalink"))
            thread_entry: Dict[str, Any] = {
                "id": post_data.get("id"),
                "title": post_data.get("title"),
                "author": post_data.get("author"),
                "score": post_data.get("score"),
                "num_comments": post_data.get("num_comments"),
                "created_utc": post_data.get("created_utc"),
                "permalink": permalink,
                "url": post_data.get("url"),
                "comments": [],
            }

            if permalink:
                comment_params = {"limit": str(comment_limit), "depth": "10", "sort": "confidence"}
                try:
                    comments_resp = client.get(
                        f"{REDDIT_OAUTH_URL}{urlsplit(permalink).path}.json",
                        params=comment_params,
                        headers=oauth_headers,
                    )
                    comments_resp.raise_for_status()
                    thread_json = comments_resp.json()
                    if len(thread_json) >= 2:
                        comment_listing = thread_json[1].get("data", {}).get("children", [])
                        thread_entry["comments"] = _extract_comments(comment_listing)
                except httpx.HTTPError as exc:  # pragma: no cover - network errors
                    logger.warning("Failed to fetch comments for %s: %s", permalink, exc)

            threads.append(thread_entry)

        return {
            "query": query,
            "subreddit": SUBREDDIT,
            "thread_count": len(threads),
            "threads": threads,
        }
    finally:
        if close_session and client is not None:
            client.close()


class RedditSearchInput(BaseModel):
    """Schema for invoking the Reddit search tool."""

    course_number: str = Field(..., description="Course identifier, e.g. 'CSE 2231'")
    teacher_name: str = Field(..., description="Instructor name to include in the search query")
    limit_threads: int = Field(5, ge=1, le=30, description="Maximum number of threads to retrieve")
    comment_limit: int = Field(100, ge=1, le=500, description="Maximum number of comments per thread")


@tool("reddit_search", args_schema=RedditSearchInput)
async def reddit_search_tool(
    course_number: str,
    teacher_name: str,
    limit_threads: int = 5,
    comment_limit: int = 100,
) -> str:
    """Fetch recent Reddit discussions about an OSU course and instructor."""

    payload = await asyncio.to_thread(
        search_reddit_threads,
        course_number,
        teacher_name,
        limit_threads=limit_threads,
        comment_limit=comment_limit,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    result = search_reddit_threads("CSE 2221", "Kevin Laeufer", limit_threads=2, comment_limit=50)
    print(result)

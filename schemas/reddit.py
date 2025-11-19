from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RedditComment(BaseModel):
    id: Optional[str] = None
    author: Optional[str] = None
    body: Optional[str] = None
    score: Optional[int] = None
    created_utc: Optional[float] = None
    permalink: Optional[str] = None
    depth: int = 0
    replies: List["RedditComment"] = Field(default_factory=list)


class RedditThread(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    score: Optional[int] = None
    num_comments: Optional[int] = None
    created_utc: Optional[float] = None
    permalink: Optional[str] = None
    url: Optional[str] = None
    comments: List[RedditComment] = Field(default_factory=list)


class RedditSearchResponse(BaseModel):
    query: str
    subreddit: str
    thread_count: int
    threads: List[RedditThread] = Field(default_factory=list)


RedditComment.model_rebuild()

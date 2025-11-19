from __future__ import annotations

from collections.abc import AsyncGenerator
import logging
import ssl
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential, before_log, after_log

if TYPE_CHECKING:  # pragma: no cover - typing helper only
    from sqlalchemy import MetaData


logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _prepare_asyncpg_url(url: str) -> tuple[str, dict[str, object]]:
    """Strip unsupported query params and translate sslmode hints for asyncpg."""
    split = urlsplit(url)
    query_pairs = parse_qsl(split.query, keep_blank_values=True)
    connect_args: dict[str, object] = {}
    kept_pairs = []

    for key, value in query_pairs:
        lowered = key.lower()
        if lowered == "sslmode":
            mode = value.lower()
            if mode in {"require", "verify-full"}:
                connect_args["ssl"] = ssl.create_default_context()
            elif mode in {"prefer", "allow", "disable"}:
                # prefer/allow behave like default asyncpg behaviour, disable forces plaintext
                if mode == "disable":
                    connect_args["ssl"] = False
            else:
                connect_args["ssl"] = ssl.create_default_context()
            continue
        if lowered == "channel_binding":
            # asyncpg does not understand channel_binding keyword; drop it.
            continue
        kept_pairs.append((key, value))

    normalized_query = urlencode(kept_pairs, doseq=True)
    normalized_url = urlunsplit(
        (split.scheme, split.netloc, split.path, normalized_query, split.fragment)
    )
    return normalized_url, connect_args


def get_engine() -> AsyncEngine:
    """Create (or reuse) the async SQLAlchemy engine configured from settings."""
    global _engine
    if _engine is None:
        database_url = settings.database_url
        connect_args: dict[str, object] = {}
        if database_url.startswith("postgresql+asyncpg://"):
            database_url, connect_args = _prepare_asyncpg_url(database_url)

        _engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory bound to the shared engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.INFO),
)
async def _create_all_with_retry(base_metadata: "MetaData") -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(base_metadata.create_all)


async def init_models(base_metadata: "MetaData") -> None:
    """Create tables for the provided SQLAlchemy metadata, retrying if the DB is still coming up."""
    await _create_all_with_retry(base_metadata)
from collections.abc import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential, before_log, after_log


_engine: AsyncEngine | None = None
_SessionFactory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Lazily create (and reuse) the async engine for the configured database."""
    global _engine
    if _engine is None:
        # Do not force SSL for asyncpg here; if SSL is needed, include it in DATABASE_URL
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory bound to the engine."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _SessionFactory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.INFO),
)
async def _create_all_with_retry(base_metadata) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(base_metadata.create_all)


async def init_models(base_metadata) -> None:
    """Create database tables for the provided SQLAlchemy Base metadata.
    Retries on transient connection failures (e.g., DB not ready at container startup).
    """
    await _create_all_with_retry(base_metadata)

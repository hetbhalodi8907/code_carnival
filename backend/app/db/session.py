from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


DB_ENGINE: AsyncEngine | None = None
DB_SESSION_FACTORY: async_sessionmaker[AsyncSession] | None = None


def create_database_engine() -> AsyncEngine:
    """Create the application-level async PostgreSQL engine."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required to create the database engine")

    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=settings.db_echo,
        future=True,
    )


def get_engine() -> AsyncEngine:
    """Return the shared application engine without connecting to PostgreSQL."""
    global DB_ENGINE
    if DB_ENGINE is None:
        DB_ENGINE = create_database_engine()
    return DB_ENGINE


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory for FastAPI dependencies."""
    global DB_SESSION_FACTORY
    if DB_SESSION_FACTORY is None:
        DB_SESSION_FACTORY = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return DB_SESSION_FACTORY


async def get_db() -> AsyncIterator[AsyncSession]:
    """Create a session for one request and close it after use."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required to create a database session")

    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def check_database_connection() -> bool:
    """Run a lightweight SELECT 1 check without loading application data."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for database connectivity checks")

    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
    return True


async def dispose_database_engine() -> None:
    """Dispose the shared engine during application shutdown."""
    global DB_ENGINE, DB_SESSION_FACTORY
    if DB_ENGINE is not None:
        await DB_ENGINE.dispose()
        DB_ENGINE = None
        DB_SESSION_FACTORY = None

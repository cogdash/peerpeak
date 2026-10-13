import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = os.environ["DATABASE_URL"]

# The application is fully async (FastAPI + grpc.aio), so we use an async engine.
# psycopg v3 supports both sync and async, which lets Alembic reuse the same URL.
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session per request."""
    async with async_session_factory() as session:
        yield session


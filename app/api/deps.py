"""Shared FastAPI dependencies.

Dependencies that open a request-scoped resource live here so routes can
inject them via ``Depends(...)`` without duplicating setup logic.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.session import async_session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async session.

    Use this for endpoints that perform normal CRUD work. The session is
    closed automatically when the dependency scope exits.

    Do **not** use this for the health endpoint: if the database is down the
    session factory raises during dependency resolution, which FastAPI
    translates into a 500 before the route body can respond with 503. Use
    :func:`get_session_factory` there instead.
    """
    async with async_session_factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the application-wide async session factory.

    Intended for endpoints (like health) that need to own the session
    lifecycle so they can degrade gracefully when the database is
    unreachable.
    """
    return async_session_factory

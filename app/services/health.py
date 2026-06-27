"""Health-checking service.

Isolated from the HTTP layer so the same health probe can be reused by
container orchestrators, startup scripts, and observability tooling without
going through FastAPI.

The service owns its own session lifecycle (opened and closed per check)
rather than accepting a request-scoped session. This is deliberate: when
the database is down, a request-scoped session dependency fails *before*
the route body runs, which surfaces as an HTTP 500. Owning the session
here lets the route translate a failed probe into a clean HTTP 503.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# asyncpg raises ConnectionRefusedError / OSError-level errors when the
# database is unreachable. SQLAlchemy does not always wrap these in
# SQLAlchemyError, so we catch OSError explicitly to degrade to 503
# instead of an unhandled 500.
_DB_ERROR_TYPES: tuple[type[BaseException], ...] = (SQLAlchemyError, OSError)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class HealthService:
    """Probes infrastructure dependencies and reports aggregate health.

    Currently the only dependency is PostgreSQL. The service is constructed
    per-request with a session *factory* (not an open session) so it can
    fail gracefully when the database is unreachable.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def check_database(self) -> bool:
        """Return ``True`` if a trivial round-trip to PostgreSQL succeeds.

        Uses ``SELECT 1`` rather than a table query so the probe works even
        before any migrations have been applied. The connection is taken
        from the application pool (``pool_pre_ping`` is enabled), so this
        also surfaces stale-connection issues.
        """
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
        except _DB_ERROR_TYPES:
            logger.exception("database_health_check_failed")
            return False
        return True

    async def get_status(self) -> dict[str, str]:
        """Return the health payload fields for the response model.

        The dict is intentionally shaped to match :class:`HealthCheckResponse`
        one-to-one, keeping the route handler trivial.
        """
        db_ok = await self.check_database()
        return {
            "status": "healthy" if db_ok else "unhealthy",
            "database": "connected" if db_ok else "disconnected",
            "version": settings.app_version,
            "environment": settings.app_env,
            "timestamp": datetime.now(UTC).isoformat(),
        }

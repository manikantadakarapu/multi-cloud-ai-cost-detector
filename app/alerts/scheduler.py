"""Small optional periodic alert evaluation loop."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.alerts.notifications import EmailNotificationService
from app.alerts.repository import AlertRepository
from app.alerts.service import AlertEvaluationService
from app.api.deps import get_session_factory
from app.auth.models import User
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.anomaly import AnomalyDetectionService
from app.services.explorer.service import CostExplorerService
from app.services.forecasting import ForecastingService

logger = get_logger(__name__)


async def run_alert_scheduler(stop_event: asyncio.Event) -> None:
    """Evaluate active users periodically when explicitly enabled by configuration."""
    config = get_settings()
    session_factory = get_session_factory()
    cache = get_cache()
    while not stop_event.is_set():
        try:
            async with session_factory() as session:
                users = (
                    (
                        await session.execute(
                            select(User).where(User.is_active.is_(True))
                        )
                    )
                    .scalars()
                    .all()
                )
                for user in users:
                    scope = str(user.id)
                    evaluator = AlertEvaluationService(
                        repo=AlertRepository(session),
                        explorer=CostExplorerService(cache=cache, user_scope=scope),
                        detector=AnomalyDetectionService(cache=cache, user_scope=scope),
                        forecasting=ForecastingService(cache=cache, user_scope=scope),
                        notifier=EmailNotificationService(config),
                    )
                    end = date.today()
                    await evaluator.evaluate(
                        user.id, user.email, end - timedelta(days=30), end
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("alert_scheduler_cycle_failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=config.alerts_evaluation_interval_seconds
            )
        except TimeoutError:
            continue

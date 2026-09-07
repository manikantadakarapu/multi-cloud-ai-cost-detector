"""Database operations for user-scoped alerts."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.models import Alert


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[Alert]:
        result = await self._session.execute(
            select(Alert)
            .where(Alert.user_id == user_id)
            .order_by(Alert.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(
        self, alert_id: uuid.UUID, user_id: uuid.UUID
    ) -> Alert | None:
        result = await self._session.execute(
            select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, alert: Alert) -> Alert:
        self._session.add(alert)
        await self._session.commit()
        await self._session.refresh(alert)
        return alert

    async def save(self, alert: Alert) -> Alert:
        await self._session.commit()
        await self._session.refresh(alert)
        return alert

    async def delete(self, alert: Alert) -> None:
        await self._session.delete(alert)
        await self._session.commit()

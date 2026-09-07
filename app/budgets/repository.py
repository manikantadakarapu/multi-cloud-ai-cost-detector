"""Database operations for user-scoped budgets."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.budgets.models import Budget


class BudgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[Budget]:
        result = await self._session.execute(
            select(Budget)
            .where(Budget.user_id == user_id)
            .order_by(Budget.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(
        self, budget_id: uuid.UUID, user_id: uuid.UUID
    ) -> Budget | None:
        result = await self._session.execute(
            select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, budget: Budget) -> Budget:
        self._session.add(budget)
        await self._session.commit()
        await self._session.refresh(budget)
        return budget

    async def save(self, budget: Budget) -> Budget:
        await self._session.commit()
        await self._session.refresh(budget)
        return budget

    async def delete(self, budget: Budget) -> None:
        await self._session.delete(budget)
        await self._session.commit()

"""Database access layer for authentication.

This module is the **only** place that touches the database for auth-related
queries. It contains no business logic — just CRUD operations. The service
layer calls these functions and applies business rules.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User


class AuthRepository:
    """Repository for ``User`` persistence.

    Constructed per-request with a request-scoped :class:`AsyncSession`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    async def get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user by primary key."""
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, user: User) -> User:
        """Persist a new user and return the managed instance."""
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        """Set ``last_login_at`` to the current UTC timestamp."""
        user = await self.get_user_by_id(user_id)
        if user is not None:
            user.last_login_at = datetime.now(UTC)
            await self._session.commit()

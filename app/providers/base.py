"""Abstract base class for cloud provider implementations.

Every concrete provider (AWS, GCP, Azure, ...) must subclass
:class:`CloudProvider` and implement the four abstract methods. This
gives the rest of the application a uniform interface for
authentication, credential validation, and cost retrieval regardless of
the underlying vendor SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.providers.schemas import CostResponse


class CloudProvider(ABC):
    """Abstract base class for cloud cost providers."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return the short identifier for this provider (e.g. ``'aws'``)."""
        raise NotImplementedError

    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate against the cloud provider using configured credentials."""
        raise NotImplementedError

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Return ``True`` if the configured credentials are valid."""
        raise NotImplementedError

    @abstractmethod
    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        """Retrieve normalized costs for the given date range and granularity."""
        raise NotImplementedError

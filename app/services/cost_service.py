"""Provider-agnostic cost service for the unified cost API.

:class:`UnifiedCostService` is the single business-logic entry point used
by ``GET /api/v1/costs``. It receives a normalised request (provider
name, date range, granularity), resolves the requested
:class:`~app.providers.base.CloudProvider` via the provider registry,
and delegates the actual cost retrieval — together with caching — to
the existing :class:`~app.services.cost_aggregator.CostAggregatorService`.

Keeping this service in its own module ensures route handlers stay
focused on HTTP concerns (validation, status-code mapping, logging)
while provider resolution and response normalisation live behind one
clear seam that can be unit-tested in isolation.
"""

from __future__ import annotations

from datetime import date

from app.core.cache import RedisCache
from app.providers import CloudProvider
from app.providers.registry import resolve_provider
from app.providers.schemas import CostResponse
from app.services.cost_aggregator import CostAggregatorService

__all__ = ["UnifiedCostService"]


class UnifiedCostService:
    """Resolve a provider and fetch normalized cost data for any cloud.

    The service is constructed per request with the ``provider`` query
    parameter resolved from the route. Construction itself validates
    the provider name — unknown providers raise
    :class:`ProviderNotSupportedException` before any I/O happens.
    """

    def __init__(
        self,
        provider_name: str,
        cache: RedisCache | None = None,
    ) -> None:
        self._provider_name = provider_name
        # Raises ProviderNotSupportedException for unknown names — this is
        # the single canonical point where "unsupported provider" is
        # surfaced for the unified endpoint.
        self._provider: CloudProvider = resolve_provider(provider_name)
        # Delegate caching + provider-name validation to the existing
        # aggregator. The inner get_provider_factory call inside the
        # aggregator will succeed because resolve_provider above just
        # confirmed the name is registered.
        self._aggregator = CostAggregatorService(
            provider_name=provider_name,
            provider=self._provider,
            cache=cache,
        )

    @property
    def provider_name(self) -> str:
        """Return the provider name the service was constructed with."""
        return self._provider_name

    @property
    def provider(self) -> CloudProvider:
        """Return the resolved :class:`CloudProvider` instance."""
        return self._provider

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        """Return normalised cost data for the configured provider.

        Provider-specific exceptions raised by the underlying SDK are
        translated into the provider-agnostic hierarchy inside each
        concrete :class:`CloudProvider`, so this method only propagates
        :class:`~app.providers.exceptions.ProviderError` subclasses (or
        :class:`ProviderNotSupportedException` if the provider name
        was invalid at construction time).
        """
        return await self._aggregator.get_costs(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )

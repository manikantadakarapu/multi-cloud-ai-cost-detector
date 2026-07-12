"""Provider-independent cost aggregation and caching.

The aggregator keeps the API layer thin by combining three concerns:

* validate the requested provider exists in the registry,
* use the provider abstraction to fetch normalized cost data, and
* cache the normalized payload behind a deterministic key.

This is intentionally future-proofed for multi-provider aggregation by keeping
the provider name as an explicit input and by making the cache key derivation
provider-aware rather than route-aware.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import Depends

from app.core.cache import RedisCache, get_cache
from app.core.config import settings
from app.core.logging import get_logger
from app.providers import CloudProvider
from app.providers.exceptions import ProviderError
from app.providers.registry import get_provider, get_provider_factory
from app.providers.schemas import CostResponse

logger = get_logger(__name__)


class CostAggregatorService:
    """Aggregate normalized cost responses through the provider abstraction."""

    def __init__(
        self,
        provider_name: str,
        provider: CloudProvider,
        cache: RedisCache | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._provider = provider
        self._cache = cache
        self._validate_provider()

    def _validate_provider(self) -> None:
        """Ensure the provider is registered and matches the requested name."""
        get_provider_factory(self._provider_name)
        actual = self._provider.provider_name()
        if actual != self._provider_name:
            raise ProviderError(
                f"Provider instance '{actual}' does not match requested provider "
                f"'{self._provider_name}'",
                error_code="PROVIDER_MISMATCH",
            )

    def _cache_scope(self) -> str:
        """Return the provider/account identifier used in cache keys."""
        if self._provider_name == "azure":
            return settings.azure_subscription_id or settings.azure_tenant_id or "azure-default"
        if self._provider_name == "aws":
            return settings.aws_profile or settings.aws_default_region or "aws-default"
        return getattr(self._provider, "cache_scope", None) or self._provider_name

    def _cache_key(self, start_date: date, end_date: date, granularity: str) -> str:
        """Build a deterministic cache key for a cost query."""
        scope = self._cache_scope()
        return (
            f"costs:{self._provider_name}:{scope}:{start_date.isoformat()}:"
            f"{end_date.isoformat()}:{granularity.upper()}"
        )

    async def get_costs(
        self,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        """Return normalized cost data, consulting Redis before the provider."""
        cache_key = self._cache_key(start_date, end_date, granularity)
        cache = self._cache

        if cache is not None:
            cached = await cache.get_json(cache_key)
            if cached is not None:
                logger.info(
                    "cost_aggregation_cache_hit",
                    extra={"provider": self._provider_name},
                )
                return CostResponse.model_validate(cached)

        logger.info(
            "cost_aggregation_cache_miss",
            extra={"provider": self._provider_name},
        )
        result = await self._provider.get_costs(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )

        if cache is not None:
            await cache.set_json(cache_key, result, ttl_seconds=settings.cache_ttl_seconds)

        return result


def get_cost_aggregator(
    provider_name: str,
    provider_dependency: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Return a FastAPI dependency that builds a cost aggregator service."""
    resolved_provider_dependency = provider_dependency or get_provider(provider_name)

    async def _dependency(
        provider: CloudProvider = Depends(resolved_provider_dependency),  # noqa: B008
        cache: RedisCache = Depends(get_cache),  # noqa: B008
    ) -> CostAggregatorService:
        return CostAggregatorService(
            provider_name=provider_name,
            provider=provider,
            cache=cache,
        )

    return _dependency

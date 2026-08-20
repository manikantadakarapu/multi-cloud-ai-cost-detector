"""Deterministic analytics over normalized provider cost responses."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.cache import RedisCache
from app.providers.base import CloudProvider
from app.providers.registry import list_providers, resolve_provider
from app.providers.schemas import CostResponse
from app.schemas.analytics import (
    AnalyticsPeriod,
    AnalyticsQuery,
    AnalyticsSummary,
    ComparisonQuery,
    CostComparison,
    CostDriver,
    CostDriversResponse,
    DailyAnalytics,
    ProviderAnalytics,
    ServiceAnalytics,
)
from app.services.analytics.exceptions import (
    AnalyticsCurrencyError,
    AnalyticsNoDataError,
)
from app.services.cost_aggregator import CostAggregatorService

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value: Decimal | float | int | str) -> Decimal:
    """Convert a numeric value to a two-decimal monetary Decimal."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class AnalyticsService:
    """Calculate analytics without depending on provider SDK types."""

    def __init__(
        self,
        cache: RedisCache | None = None,
        provider_factory: Callable[[str], CloudProvider] = resolve_provider,
        user_scope: str = "shared",
    ) -> None:
        self._cache = cache
        self._provider_factory = provider_factory
        self._user_scope = user_scope

    def _provider_names(self, provider: str | None) -> list[str]:
        return [provider] if provider else sorted(list_providers())

    async def _load(
        self,
        start_date: date,
        end_date: date,
        provider: str | None = None,
    ) -> list[CostResponse]:
        names = self._provider_names(provider)

        async def load_one(name: str) -> CostResponse:
            service = CostAggregatorService(
                provider_name=name,
                provider=self._provider_factory(name),
                cache=self._cache,
            )
            return await service.get_costs(
                start_date=start_date,
                end_date=end_date,
                granularity="DAILY",
            )

        return list(await asyncio.gather(*(load_one(name) for name in names)))

    @staticmethod
    def _currency(responses: list[CostResponse], requested: str | None) -> str:
        currencies = {response.currency.upper() for response in responses}
        if requested:
            if currencies and currencies != {requested.upper()}:
                raise AnalyticsCurrencyError(
                    f"Requested currency {requested.upper()} does not match "
                    f"available currencies: {', '.join(sorted(currencies))}"
                )
            return requested.upper()
        if len(currencies) > 1:
            raise AnalyticsCurrencyError(
                "Cannot aggregate incompatible currencies: "
                + ", ".join(sorted(currencies))
            )
        return next(iter(currencies), "USD")

    @staticmethod
    def _period(start_date: date, end_date: date) -> AnalyticsPeriod:
        return AnalyticsPeriod(start=start_date, end=end_date)

    @staticmethod
    def _percentage(value: Decimal, total: Decimal) -> Decimal:
        if total == ZERO:
            return ZERO
        return (value / total * Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)

    def _provider_totals(self, responses: list[CostResponse]) -> dict[str, Decimal]:
        return {response.provider: money(response.total_cost) for response in responses}

    def _service_totals(
        self, responses: list[CostResponse]
    ) -> dict[tuple[str, str], Decimal]:
        totals: defaultdict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
        for response in responses:
            for service in response.services:
                key = (response.provider, service.service_name)
                totals[key] += money(service.cost)
        return dict(totals)

    async def summary(self, query: AnalyticsQuery) -> AnalyticsSummary:
        responses = await self._load(query.start_date, query.end_date, query.provider)
        currency = self._currency(responses, query.currency)
        total = sum((money(response.total_cost) for response in responses), ZERO)
        if not responses and query.provider:
            raise AnalyticsNoDataError()

        providers = self._provider_totals(responses)
        provider_items = [
            ProviderAnalytics(
                provider=name,
                cost=cost,
                percentage=self._percentage(cost, total),
            )
            for name, cost in sorted(
                providers.items(), key=lambda item: (-item[1], item[0])
            )
        ]
        services = self._service_totals(responses)
        service_items = [
            ServiceAnalytics(
                provider=provider,
                service_name=name,
                cost=cost,
                percentage=self._percentage(cost, total),
            )
            for (provider, name), cost in sorted(
                services.items(), key=lambda item: (-item[1], item[0])
            )[: query.top_n]
        ]
        return AnalyticsSummary(
            period=self._period(query.start_date, query.end_date),
            currency=currency,
            total_cost=total,
            provider_count=len(providers),
            service_count=len(services),
            providers=provider_items,
            top_services=service_items,
        )

    async def providers(self, query: AnalyticsQuery) -> list[ProviderAnalytics]:
        summary = await self.summary(query)
        return summary.providers

    async def services(self, query: AnalyticsQuery) -> list[ServiceAnalytics]:
        summary = await self.summary(query)
        return summary.top_services

    async def trends(self, query: AnalyticsQuery) -> list[DailyAnalytics]:
        responses = await self._load(query.start_date, query.end_date, query.provider)
        self._currency(responses, query.currency)
        daily: defaultdict[date, Decimal] = defaultdict(lambda: ZERO)
        for response in responses:
            for item in response.daily_costs:
                daily[item.date] += money(item.cost)

        if not daily and query.start_date == query.end_date and responses:
            daily[query.start_date] = sum(
                (money(response.total_cost) for response in responses), ZERO
            )
        if (
            not daily
            and responses
            and any(response.total_cost for response in responses)
        ):
            raise AnalyticsNoDataError(
                "Providers returned cost totals without daily trend data"
            )

        day = query.start_date
        result: list[DailyAnalytics] = []
        while day <= query.end_date:
            result.append(DailyAnalytics(date=day, cost=daily.get(day, ZERO)))
            day += timedelta(days=1)
        return result

    async def compare(self, query: ComparisonQuery) -> CostComparison:
        current, previous = await asyncio.gather(
            self._load(
                query.current_start_date,
                query.current_end_date,
                query.provider,
            ),
            self._load(
                query.previous_start_date,
                query.previous_end_date,
                query.provider,
            ),
        )
        return self._comparison_from_responses(query, current, previous)

    def _comparison_from_responses(
        self,
        query: ComparisonQuery,
        current: list[CostResponse],
        previous: list[CostResponse],
    ) -> CostComparison:
        currency = self._currency(current + previous, query.currency)
        current_total = sum((money(item.total_cost) for item in current), ZERO)
        previous_total = sum((money(item.total_cost) for item in previous), ZERO)
        absolute = current_total - previous_total
        percentage = (
            None
            if previous_total == ZERO
            else (absolute / previous_total * Decimal("100")).quantize(CENT)
        )
        return CostComparison(
            currency=currency,
            current_period=self._period(
                query.current_start_date, query.current_end_date
            ),
            previous_period=self._period(
                query.previous_start_date, query.previous_end_date
            ),
            current_period_cost=current_total,
            previous_period_cost=previous_total,
            absolute_change=absolute,
            percentage_change=percentage,
        )

    async def drivers(
        self, query: ComparisonQuery, top_n: int = 5
    ) -> CostDriversResponse:
        current, previous = await asyncio.gather(
            self._load(
                query.current_start_date, query.current_end_date, query.provider
            ),
            self._load(
                query.previous_start_date, query.previous_end_date, query.provider
            ),
        )
        comparison = self._comparison_from_responses(query, current, previous)
        current_providers = self._provider_totals(current)
        previous_providers = self._provider_totals(previous)
        current_services = self._service_totals(current)
        previous_services = self._service_totals(previous)
        drivers: list[CostDriver] = []

        for provider in sorted(set(current_providers) | set(previous_providers)):
            current_cost = current_providers.get(provider, ZERO)
            previous_cost = previous_providers.get(provider, ZERO)
            drivers.append(
                self._driver("provider", provider, None, current_cost, previous_cost)
            )
        for provider, name in sorted(set(current_services) | set(previous_services)):
            current_cost = current_services.get((provider, name), ZERO)
            previous_cost = previous_services.get((provider, name), ZERO)
            drivers.append(
                self._driver("service", name, provider, current_cost, previous_cost)
            )

        drivers.sort(
            key=lambda item: (-abs(item.absolute_change), item.category, item.name)
        )
        return CostDriversResponse(
            comparison=comparison,
            drivers=drivers[:top_n],
        )

    @staticmethod
    def _driver(
        category: str,
        name: str,
        provider: str | None,
        current_cost: Decimal,
        previous_cost: Decimal,
    ) -> CostDriver:
        change = current_cost - previous_cost
        percentage = (
            None
            if previous_cost == ZERO
            else (change / previous_cost * Decimal("100")).quantize(CENT)
        )
        return CostDriver(
            category=category,  # type: ignore[arg-type]
            name=name,
            provider=provider,
            current_cost=current_cost,
            previous_cost=previous_cost,
            absolute_change=change,
            percentage_change=percentage,
        )

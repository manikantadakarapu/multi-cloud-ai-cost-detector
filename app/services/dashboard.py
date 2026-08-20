"""Dashboard composition and deterministic insight generation."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from app.core.cache import RedisCache
from app.schemas.analytics import AnalyticsQuery, ComparisonQuery
from app.schemas.dashboard import DashboardOverview, DashboardSummary
from app.schemas.insights import (
    CostInsight,
    DashboardInsights,
    InsightSeverity,
    InsightType,
)
from app.services.analytics.service import AnalyticsService

INSIGHT_PERCENTAGE_THRESHOLD = Decimal("5.00")


class DashboardService:
    """Compose existing analytics into frontend contracts without AI calls."""

    def __init__(
        self,
        analytics: AnalyticsService,
        cache: RedisCache | None = None,
        user_scope: str = "shared",
    ) -> None:
        self._analytics = analytics
        self._cache = cache
        self._user_scope = user_scope

    @staticmethod
    def _previous_period(query: AnalyticsQuery) -> tuple[date, date]:
        period_length = query.end_date - query.start_date + timedelta(days=1)
        previous_end = query.start_date - timedelta(days=1)
        return previous_end - period_length + timedelta(days=1), previous_end

    def _cache_key(self, operation: str, query: AnalyticsQuery) -> str:
        provider = query.provider or "all"
        currency = query.currency or "default"
        return (
            f"dashboard:{operation}:{self._user_scope}:{query.start_date}:"
            f"{query.end_date}:{provider}:{currency}:{query.top_n}"
        )

    async def _get_cached(self, key: str, model):  # noqa: ANN001
        if self._cache is None:
            return None
        payload = await self._cache.get_json(key)
        return model.model_validate(payload) if payload is not None else None

    async def summary(self, query: AnalyticsQuery) -> DashboardSummary:
        key = self._cache_key("summary", query)
        cached = await self._get_cached(key, DashboardSummary)
        if cached is not None:
            return cached

        previous_start, previous_end = self._previous_period(query)
        comparison_query = ComparisonQuery(
            current_start_date=query.start_date,
            current_end_date=query.end_date,
            previous_start_date=previous_start,
            previous_end_date=previous_end,
            provider=query.provider,
            currency=query.currency,
            top_n=query.top_n,
        )
        summary, trend, drivers = await asyncio.gather(
            self._analytics.summary(query),
            self._analytics.trends(query),
            self._analytics.drivers(comparison_query, top_n=query.top_n),
        )
        comparison = drivers.comparison
        result = DashboardSummary(
            overview=DashboardOverview(
                total_cost=summary.total_cost,
                currency=summary.currency,
                period_start=query.start_date,
                period_end=query.end_date,
                previous_period_cost=comparison.previous_period_cost,
                absolute_change=comparison.absolute_change,
                percentage_change=comparison.percentage_change,
            ),
            providers=summary.providers,
            services=summary.top_services,
            trend=trend,
            drivers=drivers.drivers,
        )
        if self._cache is not None:
            await self._cache.set_json(key, result)
        return result

    async def insights(self, query: AnalyticsQuery) -> DashboardInsights:
        key = self._cache_key("insights", query)
        cached = await self._get_cached(key, DashboardInsights)
        if cached is not None:
            return cached

        dashboard = await self.summary(query)
        insights = self._generate_insights(dashboard)
        result = DashboardInsights(insights=insights)
        if self._cache is not None:
            await self._cache.set_json(key, result)
        return result

    @staticmethod
    def _severity(percentage: Decimal | None, impact: Decimal) -> InsightSeverity:
        if percentage is None or abs(percentage) >= Decimal("25.00"):
            return InsightSeverity.HIGH
        if abs(percentage) >= Decimal("10.00") or abs(impact) >= Decimal("100.00"):
            return InsightSeverity.MEDIUM
        return InsightSeverity.LOW

    @classmethod
    def _generate_insights(cls, dashboard: DashboardSummary) -> list[CostInsight]:
        overview = dashboard.overview
        insights: list[CostInsight] = []
        change = overview.absolute_change
        percentage = overview.percentage_change
        significant = (
            percentage is None or abs(percentage) >= INSIGHT_PERCENTAGE_THRESHOLD
        )
        if significant and change > 0:
            insights.append(
                CostInsight(
                    type=InsightType.COST_INCREASE,
                    severity=cls._severity(percentage, change),
                    title="Cloud costs increased",
                    description=cls._change_description(
                        "increased", percentage, change, overview.currency
                    ),
                    impact=change,
                    currency=overview.currency,
                )
            )
        elif significant and change < 0:
            insights.append(
                CostInsight(
                    type=InsightType.COST_DECREASE,
                    severity=cls._severity(percentage, change),
                    title="Cloud costs decreased",
                    description=cls._change_description(
                        "decreased", percentage, abs(change), overview.currency
                    ),
                    impact=abs(change),
                    currency=overview.currency,
                )
            )

        for driver in dashboard.drivers:
            if driver.category != "service" or driver.absolute_change <= 0:
                continue
            insights.append(
                CostInsight(
                    type=InsightType.TOP_COST_DRIVER,
                    severity=cls._severity(
                        driver.percentage_change, driver.absolute_change
                    ),
                    title=f"{driver.name} is the top cost driver",
                    description=(
                        f"{driver.name} increased by {driver.absolute_change:.2f} "
                        f"{overview.currency} compared with the previous period."
                    ),
                    provider=driver.provider,
                    service=driver.name,
                    impact=driver.absolute_change,
                    currency=overview.currency,
                )
            )
            break
        return insights

    @staticmethod
    def _change_description(
        verb: str,
        percentage: Decimal | None,
        impact: Decimal,
        currency: str,
    ) -> str:
        rate = f" by {abs(percentage):.2f}%" if percentage is not None else ""
        return f"Total costs {verb}{rate}, a change of {impact:.2f} {currency}."

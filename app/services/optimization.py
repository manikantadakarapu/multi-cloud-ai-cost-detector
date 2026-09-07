"""Deterministic FinOps optimization recommendations from normalized cost data."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.core.cache import RedisCache
from app.core.logging import get_logger
from app.schemas.explorer import CostRecord
from app.schemas.optimization import (
    OptimizationQuery,
    OptimizationResponse,
    OptimizationSummary,
    Recommendation,
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationEvidence,
    RecommendationPriority,
    RecommendationSort,
    RecommendationStatus,
)
from app.services.explorer.service import CostExplorerService

logger = get_logger(__name__)

RULE_VERSION = "optimization-rules-v1"
CENT = Decimal("0.01")
ZERO = Decimal("0")
MIN_DAYS = 14
GROWTH_THRESHOLD = Decimal("0.20")
HIGH_COST_SHARE = Decimal("0.20")
PRIORITY_RANK = {
    RecommendationPriority.LOW: 0,
    RecommendationPriority.MEDIUM: 1,
    RecommendationPriority.HIGH: 2,
    RecommendationPriority.CRITICAL: 3,
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _average(values: Iterable[Decimal]) -> Decimal:
    values = list(values)
    return sum(values, ZERO) / Decimal(len(values)) if values else ZERO


def _filter_records(
    records: Iterable[CostRecord], query: OptimizationQuery
) -> list[CostRecord]:
    result = []
    for record in records:
        if record.date < query.start_date or record.date > query.end_date:
            continue
        if query.provider and record.provider.lower() != query.provider.lower():
            continue
        if query.account_id and (
            not record.account_id
            or query.account_id.lower() not in record.account_id.lower()
        ):
            continue
        if query.service and query.service.lower() not in record.service.lower():
            continue
        if query.region and (
            not record.region or query.region.lower() not in record.region.lower()
        ):
            continue
        result.append(record)
    return result


def _deduplicate(records: Iterable[CostRecord]) -> list[CostRecord]:
    seen: set[tuple[object, ...]] = set()
    result = []
    for record in records:
        key = (
            record.date,
            record.provider,
            record.account_id,
            record.service,
            record.region,
            record.cost,
            record.currency,
        )
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def _daily(records: Iterable[CostRecord]) -> dict[date, Decimal]:
    totals: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for record in records:
        if record.cost >= ZERO:
            totals[record.date] += record.cost
    return dict(totals)


def _monthly_savings(recent: Decimal, baseline: Decimal) -> tuple[Decimal, Decimal]:
    delta = max(ZERO, recent - baseline) * Decimal("30")
    return _money(delta * Decimal("0.50")), _money(delta)


def _priority(
    monthly_savings: Decimal | None, current_cost: Decimal, share: Decimal
) -> RecommendationPriority:
    if monthly_savings is not None and monthly_savings >= Decimal("1000"):
        return RecommendationPriority.CRITICAL
    if (
        monthly_savings is not None and monthly_savings >= Decimal("250")
    ) or share >= Decimal("0.40"):
        return RecommendationPriority.HIGH
    if current_cost >= Decimal("300") or share >= HIGH_COST_SHARE:
        return RecommendationPriority.MEDIUM
    return RecommendationPriority.LOW


def _category_for_service(service: str) -> RecommendationCategory:
    lowered = service.lower()
    if any(term in lowered for term in ("storage", "s3", "blob", "disk", "volume")):
        return RecommendationCategory.STORAGE
    if any(
        term in lowered
        for term in ("network", "transfer", "egress", "cdn", "bandwidth")
    ):
        return RecommendationCategory.NETWORK
    return RecommendationCategory.COST_GROWTH


class OptimizationService:
    """Generate, cache, filter, and lifecycle-manage advisory recommendations."""

    def __init__(
        self,
        cache: RedisCache | None = None,
        user_scope: str = "shared",
        explorer: CostExplorerService | None = None,
    ) -> None:
        self._cache = cache
        self._user_scope = user_scope
        self._explorer = explorer or CostExplorerService(
            cache=cache, user_scope=user_scope
        )

    def _cache_key(self, query: OptimizationQuery) -> str:
        digest = hashlib.sha256(query.model_dump_json().encode()).hexdigest()[:20]
        return f"optimization:{self._user_scope}:{RULE_VERSION}:{digest}"

    def _status_key(self, recommendation_id: str) -> str:
        return f"optimization-status:{self._user_scope}:{recommendation_id}"

    async def _status(self, recommendation_id: str) -> RecommendationStatus:
        if self._cache is None:
            return RecommendationStatus.NEW
        value = await self._cache.get_json(self._status_key(recommendation_id))
        try:
            return (
                RecommendationStatus(value["status"])
                if value
                else RecommendationStatus.NEW
            )
        except (KeyError, TypeError, ValueError):
            return RecommendationStatus.NEW

    async def _apply_statuses(
        self, recommendations: list[Recommendation]
    ) -> list[Recommendation]:
        result = []
        for recommendation in recommendations:
            recommendation.status = await self._status(recommendation.recommendation_id)
            result.append(recommendation)
        return result

    def _recommendation(
        self,
        *,
        group_key: tuple[str, str | None, str, str | None],
        category: RecommendationCategory,
        records: list[CostRecord],
        baseline: Decimal,
        recent: Decimal,
        total_cost: Decimal,
        method: str,
        description: str,
    ) -> Recommendation:
        provider, account_id, service, region = group_key
        current_cost = _money(recent * Decimal("30"))
        share = recent / total_cost if total_cost else ZERO
        growth = (recent - baseline) / baseline if baseline else ZERO
        lower, upper = _monthly_savings(recent, baseline)
        savings = upper if upper > ZERO else None
        confidence = (
            RecommendationConfidence.HIGH
            if len(_daily(records)) >= 21
            else RecommendationConfidence.MEDIUM
        )
        priority = _priority(savings, current_cost, share)
        currency = records[0].currency
        identity = "|".join(
            (
                provider,
                account_id or "",
                service,
                region or "",
                category.value,
                method,
                RULE_VERSION,
            )
        )
        recommendation_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
        evidence = [
            RecommendationEvidence(
                label="Recent daily average",
                value=f"{_money(recent)} {currency}",
                source="normalized Cost Explorer records",
            ),
            RecommendationEvidence(
                label="Earlier daily average",
                value=f"{_money(baseline)} {currency}",
                source="normalized Cost Explorer records",
            ),
            RecommendationEvidence(
                label="Sustained change",
                value=f"{_money(growth * Decimal('100'))}%",
                source="deterministic comparison of historical periods",
            ),
            RecommendationEvidence(
                label="Share of filtered spend",
                value=f"{_money(share * Decimal('100'))}%",
                source="normalized Cost Explorer records",
            ),
        ]
        return Recommendation(
            recommendation_id=recommendation_id,
            provider=provider,
            account_id=account_id,
            service=service,
            region=region,
            category=category,
            title=f"Investigate sustained {service} cost growth",
            description=description,
            rationale=(
                "The recent cost level is materially above the earlier comparable "
                "period and persisted across the available history."
            ),
            evidence=evidence,
            priority=priority,
            current_cost=current_cost,
            estimated_monthly_savings=savings,
            estimated_annual_savings=(
                _money(savings * Decimal("12")) if savings is not None else None
            ),
            savings_currency=currency,
            savings_explanation=(
                f"Scenario range: {_money(lower)}–{_money(upper)} {currency}/month "
                "if spend returns toward the earlier baseline; this is advisory, "
                "not a guaranteed saving."
            ),
            confidence=confidence,
            detection_method=method,
            rule_version=RULE_VERSION,
            created_at=datetime.now(UTC),
        )

    def _build_recommendations(
        self, records: list[CostRecord], query: OptimizationQuery
    ) -> list[Recommendation]:
        if not records:
            return []
        grouped: dict[tuple[str, str | None, str, str | None], list[CostRecord]] = (
            defaultdict(list)
        )
        for record in records:
            grouped[
                (record.provider, record.account_id, record.service, record.region)
            ].append(record)
        recommendations: list[Recommendation] = []
        group_metrics: dict[
            tuple[str, str | None, str, str | None],
            tuple[dict[date, Decimal], Decimal, Decimal],
        ] = {}
        for key, group in grouped.items():
            daily = _daily(group)
            if len(daily) < MIN_DAYS:
                continue
            ordered = [daily[day] for day in sorted(daily)]
            midpoint = len(ordered) // 2
            group_metrics[key] = (
                daily,
                _average(ordered[:midpoint]),
                _average(ordered[midpoint:]),
            )
        total_cost = sum((metrics[2] for metrics in group_metrics.values()), ZERO)
        for key, group in grouped.items():
            metrics = group_metrics.get(key)
            if metrics is None:
                continue
            daily, baseline, recent = metrics
            growth = (recent - baseline) / baseline if baseline else ZERO
            share = recent / total_cost if total_cost else ZERO
            category = _category_for_service(key[2])
            if baseline > ZERO and growth >= GROWTH_THRESHOLD:
                label = category.value.replace("_", " ")
                recommendations.append(
                    self._recommendation(
                        group_key=key,
                        category=category,
                        records=group,
                        baseline=baseline,
                        recent=recent,
                        total_cost=total_cost,
                        method=f"sustained_{label}_growth",
                        description=(
                            f"Review the sustained {label} pattern in Cost Explorer "
                            "before making any infrastructure change."
                        ),
                    )
                )
            if share >= HIGH_COST_SHARE and recent * Decimal("30") >= Decimal("300"):
                recommendations.append(
                    self._recommendation(
                        group_key=key,
                        category=RecommendationCategory.HIGH_COST_SERVICE,
                        records=group,
                        baseline=baseline,
                        recent=recent,
                        total_cost=total_cost,
                        method="persistent_high_cost_service",
                        description=(
                            "This service is a material share of filtered spend; "
                            "investigate its drivers and usage before selecting an "
                            "optimization."
                        ),
                    )
                )
        return recommendations

    @staticmethod
    def _sort(
        recommendations: list[Recommendation], query: OptimizationQuery
    ) -> list[Recommendation]:
        if query.sort_by is RecommendationSort.PRIORITY:

            def key(item: Recommendation) -> int:
                return PRIORITY_RANK[item.priority]

        elif query.sort_by is RecommendationSort.CREATED_DATE:

            def key(item: Recommendation) -> datetime:
                return item.created_at

        else:

            def key(item: Recommendation) -> Decimal:
                return item.estimated_monthly_savings or ZERO

        return sorted(recommendations, key=key, reverse=query.sort_order == "desc")

    @staticmethod
    def _summary(recommendations: list[Recommendation]) -> OptimizationSummary:
        monthly_values = [
            item.estimated_monthly_savings
            for item in recommendations
            if item.estimated_monthly_savings is not None
        ]
        return OptimizationSummary(
            total_recommendations=len(recommendations),
            high_or_critical=sum(
                item.priority
                in {RecommendationPriority.HIGH, RecommendationPriority.CRITICAL}
                for item in recommendations
            ),
            estimated_monthly_savings=(
                _money(sum(monthly_values, ZERO)) if monthly_values else None
            ),
            estimated_annual_savings=(
                _money(
                    sum(
                        (
                            item.estimated_annual_savings or ZERO
                            for item in recommendations
                        ),
                        ZERO,
                    )
                )
                if monthly_values
                else None
            ),
            by_category=dict(
                sorted(
                    {
                        category.value: sum(
                            item.category is category for item in recommendations
                        )
                        for category in RecommendationCategory
                        if any(item.category is category for item in recommendations)
                    }.items()
                )
            ),
            by_provider=dict(
                sorted(
                    {
                        provider: sum(
                            item.provider == provider for item in recommendations
                        )
                        for provider in {item.provider for item in recommendations}
                    }.items()
                )
            ),
        )

    async def list_recommendations(
        self, query: OptimizationQuery
    ) -> OptimizationResponse:
        cache_key = self._cache_key(query)
        recommendations: list[Recommendation] | None = None
        if self._cache is not None:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                try:
                    recommendations = [
                        Recommendation.model_validate(item) for item in cached
                    ]
                except Exception:
                    logger.warning("optimization_cache_invalid")
        if recommendations is None:
            records = await self._explorer.get_cost_records(
                query.start_date, query.end_date, query.provider
            )
            recommendations = self._build_recommendations(
                _deduplicate(_filter_records(records, query)), query
            )
            if self._cache is not None:
                await self._cache.set_json(cache_key, recommendations, 3600)
        recommendations = await self._apply_statuses(recommendations)
        if query.category:
            recommendations = [
                item for item in recommendations if item.category is query.category
            ]
        if query.priority:
            recommendations = [
                item for item in recommendations if item.priority is query.priority
            ]
        if query.status:
            recommendations = [
                item for item in recommendations if item.status is query.status
            ]
        recommendations = self._sort(recommendations, query)
        total = len(recommendations)
        page = recommendations[query.offset : query.offset + query.limit]
        message = (
            None
            if recommendations
            else "No evidence-backed optimization recommendations matched the filters."
        )
        return OptimizationResponse(
            recommendations=page,
            total=total,
            limit=query.limit,
            offset=query.offset,
            summary=self._summary(recommendations),
            query=query,
            rule_version=RULE_VERSION,
            insufficient_data=not bool(recommendations),
            message=message,
        )

    async def get_recommendation(
        self, recommendation_id: str, query: OptimizationQuery
    ) -> Recommendation | None:
        lookup = query.model_copy(update={"limit": 100, "offset": 0, "status": None})
        response = await self.list_recommendations(lookup)
        return next(
            (
                item
                for item in response.recommendations
                if item.recommendation_id == recommendation_id
            ),
            None,
        )

    async def update_status(
        self,
        recommendation_id: str,
        status: RecommendationStatus,
        query: OptimizationQuery,
    ) -> Recommendation | None:
        recommendation = await self.get_recommendation(recommendation_id, query)
        if recommendation is None:
            return None
        if self._cache is not None:
            await self._cache.set_json(
                self._status_key(recommendation_id),
                {"status": status.value},
                86400 * 30,
            )
        recommendation.status = status
        return recommendation

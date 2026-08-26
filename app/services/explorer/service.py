"""Provider-independent Cost Explorer service for multi-dimensional spend drill-down."""

from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.cache import RedisCache
from app.core.logging import get_logger
from app.providers.base import CloudProvider
from app.providers.registry import list_providers, resolve_provider
from app.providers.schemas import CostResponse
from app.schemas.explorer import (
    AvailableFilters,
    CostRecord,
    DailyCostRecord,
    DimensionBreakdowns,
    DimensionTotal,
    ExplorerOverview,
    ExplorerQuery,
    ExplorerResponse,
)

logger = get_logger(__name__)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
EXPLORER_CACHE_TTL = 3600


def money(value: Decimal | float | int | str) -> Decimal:
    """Convert numeric value to a two-decimal monetary Decimal."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class CostExplorerService:
    """Orchestrates multi-provider line-item loading, filtering, aggregation, and caching."""

    def __init__(
        self,
        cache: RedisCache | None = None,
        provider_factory: Callable[[str], CloudProvider] = resolve_provider,
        user_scope: str = "shared",
    ) -> None:
        self._cache = cache
        self._provider_factory = provider_factory
        self._user_scope = user_scope

    def _cache_key(self, query: ExplorerQuery) -> str:
        payload = query.model_dump_json(exclude_none=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"explorer:{self._user_scope}:{digest}"

    def _target_providers(self, provider_filter: str | None) -> list[str]:
        if provider_filter:
            return [provider_filter]
        return sorted(list_providers())

    async def _fetch_provider_records(
        self,
        provider_name: str,
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> list[CostRecord]:
        """Fetch records from a provider using explorer method or normalized fallback."""
        try:
            provider = self._provider_factory(provider_name)
            if hasattr(provider, "get_explorer_records") and callable(
                provider.get_explorer_records
            ):
                return await provider.get_explorer_records(
                    start_date, end_date, granularity
                )

            # Fallback: extract records from standard CostResponse
            cost_response: CostResponse = await provider.get_costs(
                start_date, end_date, granularity
            )
            records: list[CostRecord] = []

            currency = cost_response.currency or "USD"
            if cost_response.daily_costs and cost_response.services:
                total_svc_cost = sum(s.cost for s in cost_response.services) or 1.0
                for day in cost_response.daily_costs:
                    day_ratio = day.cost / total_svc_cost if total_svc_cost else 1.0
                    for svc in cost_response.services:
                        allocated_cost = money(
                            Decimal(str(svc.cost)) * Decimal(str(day_ratio))
                        )
                        if allocated_cost > 0:
                            records.append(
                                CostRecord(
                                    date=day.date,
                                    provider=provider_name,
                                    account_id=f"{provider_name}-account",
                                    account_name=f"{provider_name.upper()} Main Account",
                                    service=svc.service_name,
                                    region="global",
                                    cost=allocated_cost,
                                    currency=currency,
                                )
                            )
            elif cost_response.services:
                for svc in cost_response.services:
                    records.append(
                        CostRecord(
                            date=start_date,
                            provider=provider_name,
                            account_id=f"{provider_name}-account",
                            account_name=f"{provider_name.upper()} Main Account",
                            service=svc.service_name,
                            region="global",
                            cost=money(svc.cost),
                            currency=currency,
                        )
                    )
            elif cost_response.total_cost > 0:
                records.append(
                    CostRecord(
                        date=start_date,
                        provider=provider_name,
                        account_id=f"{provider_name}-account",
                        account_name=f"{provider_name.upper()} Main Account",
                        service=f"{provider_name.upper()} Total",
                        region="global",
                        cost=money(cost_response.total_cost),
                        currency=currency,
                    )
                )
            return records
        except Exception as error:
            logger.warning(
                "explorer_provider_fetch_failed",
                extra={"provider": provider_name, "error": str(error)},
            )
            return []

    async def _load_all_records(
        self,
        start_date: date,
        end_date: date,
        provider_filter: str | None,
        granularity: str,
    ) -> list[CostRecord]:
        providers = self._target_providers(provider_filter)
        tasks = [
            self._fetch_provider_records(p, start_date, end_date, granularity)
            for p in providers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_records: list[CostRecord] = []
        for r in results:
            if isinstance(r, list):
                all_records.extend(r)
        return all_records

    def _apply_filters(
        self, records: list[CostRecord], query: ExplorerQuery
    ) -> list[CostRecord]:
        filtered: list[CostRecord] = []
        for rec in records:
            if rec.date < query.start_date or rec.date > query.end_date:
                continue
            if query.provider and rec.provider.lower() != query.provider.lower():
                continue
            if (
                query.account_id
                and rec.account_id
                and query.account_id.lower() not in rec.account_id.lower()
            ):
                continue
            if query.service and query.service.lower() not in rec.service.lower():
                continue
            if (
                query.region
                and rec.region
                and query.region.lower() not in rec.region.lower()
            ):
                continue
            filtered.append(rec)
        return filtered

    def _aggregate(
        self, records: list[CostRecord], query: ExplorerQuery
    ) -> ExplorerResponse:
        total_cost = sum((r.cost for r in records), ZERO)
        currency = records[0].currency if records else "USD"

        # Breakdowns
        provider_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        provider_counts: dict[str, int] = defaultdict(int)

        service_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        service_counts: dict[str, int] = defaultdict(int)

        region_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        region_counts: dict[str, int] = defaultdict(int)

        account_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        account_counts: dict[str, int] = defaultdict(int)

        daily_totals: dict[date, Decimal] = defaultdict(lambda: ZERO)

        # Available filters
        avail_providers = set()
        avail_accounts = set()
        avail_services = set()
        avail_regions = set()

        for rec in records:
            provider_totals[rec.provider] += rec.cost
            provider_counts[rec.provider] += 1
            avail_providers.add(rec.provider)

            service_totals[rec.service] += rec.cost
            service_counts[rec.service] += 1
            avail_services.add(rec.service)

            reg = rec.region or "global"
            region_totals[reg] += rec.cost
            region_counts[reg] += 1
            avail_regions.add(reg)

            acc = rec.account_name or rec.account_id or "default"
            account_totals[acc] += rec.cost
            account_counts[acc] += 1
            if rec.account_id:
                avail_accounts.add(rec.account_id)

            daily_totals[rec.date] += rec.cost

        def build_dimension_list(
            totals: dict[str, Decimal], counts: dict[str, int]
        ) -> list[DimensionTotal]:
            result: list[DimensionTotal] = []
            for key, cost_amt in totals.items():
                pct = (
                    money((cost_amt / total_cost) * Decimal("100.00"))
                    if total_cost > ZERO
                    else ZERO
                )
                label = (
                    "GCP"
                    if key.lower() == "gcp"
                    else key.upper() if len(key) <= 4 else key
                )
                result.append(
                    DimensionTotal(
                        key=key,
                        label=label,
                        cost=money(cost_amt),
                        percentage=pct,
                        currency=currency,
                        record_count=counts[key],
                    )
                )
            result.sort(key=lambda x: x.cost, reverse=True)
            return result

        by_provider = build_dimension_list(provider_totals, provider_counts)
        by_service = build_dimension_list(service_totals, service_counts)
        by_region = build_dimension_list(region_totals, region_counts)
        by_account = build_dimension_list(account_totals, account_counts)

        by_date = [
            DailyCostRecord(date=d, cost=money(c), currency=currency)
            for d, c in sorted(daily_totals.items())
        ]

        overview = ExplorerOverview(
            total_cost=money(total_cost),
            currency=currency,
            record_count=len(records),
            start_date=query.start_date,
            end_date=query.end_date,
        )

        available_filters = AvailableFilters(
            providers=sorted(avail_providers),
            accounts=sorted(avail_accounts),
            services=sorted(avail_services),
            regions=sorted(avail_regions),
        )

        records_sorted = sorted(records, key=lambda r: (r.date, r.cost), reverse=True)
        paginated_records = records_sorted[query.offset : query.offset + query.limit]

        return ExplorerResponse(
            overview=overview,
            records=paginated_records,
            dimension_totals=DimensionBreakdowns(
                by_provider=by_provider,
                by_service=by_service,
                by_region=by_region,
                by_account=by_account,
                by_date=by_date,
            ),
            available_filters=available_filters,
            total_records=len(records),
            limit=query.limit,
            offset=query.offset,
        )

    async def get_explorer_data(self, query: ExplorerQuery) -> ExplorerResponse:
        """Retrieve, filter, and aggregate multi-cloud cost records with Redis caching."""
        cache_key = self._cache_key(query)
        if self._cache is not None:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                try:
                    return ExplorerResponse.model_validate_json(cached)
                except Exception as err:
                    logger.debug(
                        "explorer_cache_parse_failed", extra={"error": str(err)}
                    )

        raw_records = await self._load_all_records(
            start_date=query.start_date,
            end_date=query.end_date,
            provider_filter=query.provider,
            granularity=query.granularity,
        )
        filtered_records = self._apply_filters(raw_records, query)
        response = self._aggregate(filtered_records, query)

        if self._cache is not None:
            await self._cache.set(
                cache_key, response.model_dump_json(), ttl=EXPLORER_CACHE_TTL
            )

        return response

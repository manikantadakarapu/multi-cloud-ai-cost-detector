"""Deterministic provider-independent cost forecasting."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.cache import RedisCache
from app.core.logging import get_logger
from app.schemas.explorer import CostRecord
from app.schemas.forecast import (
    DailyActual,
    DailyForecast,
    ForecastAccuracy,
    ForecastDataQuality,
    ForecastDimension,
    ForecastQuery,
    ForecastResponse,
    ForecastResult,
    ForecastStatus,
    ForecastSummary,
)
from app.services.explorer.service import CostExplorerService

logger = get_logger(__name__)

METHODOLOGY_VERSION = "weighted-trend-v1"
MIN_OBSERVATIONS = 7
CENT = Decimal("0.01")
ZERO = Decimal("0")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _filter_records(
    records: Iterable[CostRecord], query: ForecastQuery
) -> list[CostRecord]:
    filtered = []
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
        if query.currency and record.currency.upper() != query.currency.upper():
            continue
        filtered.append(record)
    return filtered


def _unique_records(records: Iterable[CostRecord]) -> tuple[list[CostRecord], int]:
    seen: set[tuple[object, ...]] = set()
    unique: list[CostRecord] = []
    duplicates = 0
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
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(record)
    return unique, duplicates


def _group_records(
    records: Iterable[CostRecord], dimension: ForecastDimension
) -> dict[str, list[CostRecord]]:
    grouped: dict[str, list[CostRecord]] = defaultdict(list)
    for record in records:
        if dimension is ForecastDimension.TOTAL:
            key = "all"
        elif dimension is ForecastDimension.PROVIDER:
            key = record.provider
        elif dimension is ForecastDimension.SERVICE:
            key = record.service
        elif dimension is ForecastDimension.ACCOUNT:
            key = record.account_id or "unknown"
        else:
            key = record.region or "global"
        grouped[key].append(record)
    return dict(grouped)


def _daily_values(
    records: Iterable[CostRecord], start: date, end: date
) -> tuple[list[tuple[date, Decimal]], list[date]]:
    totals: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for record in records:
        if record.cost < ZERO:
            continue
        totals[record.date] += record.cost
    values: list[tuple[date, Decimal]] = []
    missing: list[date] = []
    current = start
    while current <= end:
        if current not in totals:
            missing.append(current)
        values.append((current, totals.get(current, ZERO)))
        current += timedelta(days=1)
    return values, missing


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _clean_outliers(
    values: list[tuple[date, Decimal]],
) -> tuple[list[tuple[date, Decimal]], list[date]]:
    if len(values) < MIN_OBSERVATIONS:
        return values, []
    median = _median([value for _, value in values])
    deviations = [abs(value - median) for _, value in values]
    mad = _median(deviations)
    if mad == ZERO:
        threshold = median * Decimal("3") if median > ZERO else ZERO
    else:
        threshold = median + Decimal("3") * mad
    excluded = [day for day, value in values if value > threshold and value > median]
    if len(excluded) >= len(values) - 2:
        return values, []
    excluded_set = set(excluded)
    return [(day, value) for day, value in values if day not in excluded_set], excluded


def _weighted_level(values: list[Decimal]) -> Decimal:
    recent = values[-min(7, len(values)) :]
    weights = range(1, len(recent) + 1)
    return sum(
        (value * weight for value, weight in zip(recent, weights, strict=True)), ZERO
    ) / Decimal(sum(weights))


def _slope(values: list[Decimal]) -> Decimal:
    count = Decimal(len(values))
    mean_x = (count - 1) / Decimal("2")
    mean_y = sum(values, ZERO) / count
    numerator = sum(
        (Decimal(index) - mean_x) * (value - mean_y)
        for index, value in enumerate(values)
    )
    denominator = sum((Decimal(index) - mean_x) ** 2 for index in range(len(values)))
    return numerator / denominator if denominator else ZERO


def _confidence(level: Decimal, spread: Decimal, points: int) -> str:
    if level <= ZERO:
        return "low"
    ratio = spread / level
    if points >= 21 and ratio <= Decimal("0.15"):
        return "high"
    if points >= MIN_OBSERVATIONS and ratio <= Decimal("0.35"):
        return "medium"
    return "low"


def calculate_accuracy(
    forecast: ForecastResult, actuals: dict[date, Decimal]
) -> ForecastAccuracy:
    """Compare completed daily forecasts with normalized actual costs."""
    pairs = [
        (point.forecast_cost, actuals[point.date])
        for point in forecast.daily_forecast
        if point.date in actuals
    ]
    if not pairs:
        return ForecastAccuracy(observations=0, mean_absolute_error=ZERO)
    errors = [abs(expected - actual) for expected, actual in pairs]
    valid_mape = [
        error / actual * Decimal("100")
        for error, (_, actual) in zip(errors, pairs, strict=True)
        if actual > ZERO
    ]
    return ForecastAccuracy(
        observations=len(pairs),
        mean_absolute_error=_quantize(sum(errors, ZERO) / Decimal(len(errors))),
        mean_absolute_percentage_error=(
            _quantize(sum(valid_mape, ZERO) / Decimal(len(valid_mape)))
            if valid_mape
            else None
        ),
    )


class ForecastingService:
    """Loads normalized Cost Explorer records and produces deterministic forecasts."""

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

    def _cache_key(self, query: ForecastQuery) -> str:
        digest = hashlib.sha256(query.model_dump_json().encode()).hexdigest()[:20]
        return f"forecast:{self._user_scope}:{METHODOLOGY_VERSION}:{digest}"

    @staticmethod
    def _empty_response(
        query: ForecastQuery, quality: ForecastDataQuality, message: str
    ) -> ForecastResponse:
        return ForecastResponse(
            status=(
                ForecastStatus.EMPTY
                if quality.available_observations == 0
                else ForecastStatus.INSUFFICIENT_DATA
            ),
            query=query,
            summary=ForecastSummary(
                current_spend=ZERO,
                projected_spend=ZERO,
                projected_change_percentage=None,
                average_historical_daily_cost=ZERO,
                projected_daily_average=ZERO,
                confidence=None,
                data_points_used=quality.available_observations,
            ),
            data_quality=quality,
            methodology_version=METHODOLOGY_VERSION,
            message=message,
        )

    def _forecast_group(
        self,
        key: str,
        records: list[CostRecord],
        query: ForecastQuery,
        missing: list[date],
    ) -> ForecastResult | None:
        daily, _ = _daily_values(records, query.start_date, query.end_date)
        if len(daily) < MIN_OBSERVATIONS:
            return None
        cleaned, excluded = _clean_outliers(daily)
        values = [value for _, value in cleaned]
        level = _weighted_level(values)
        trend = _slope(values)
        # A bounded trend keeps long horizons explainable and prevents one noisy
        # slope from exploding.
        max_trend = max(level * Decimal("0.50"), Decimal("0.01"))
        trend = max(-max_trend, min(max_trend, trend))
        residuals = []
        for index, value in enumerate(values):
            fitted = level + trend * Decimal(index - len(values) + 1)
            residuals.append(abs(value - fitted))
        spread = max(
            _median(residuals) * Decimal("2"), level * Decimal("0.10"), Decimal("0.01")
        )
        confidence = _confidence(level, spread, len(values))
        forecast_start = query.end_date + timedelta(days=1)
        daily_forecast: list[DailyForecast] = []
        for step in range(1, query.horizon_days + 1):
            expected = max(ZERO, level + trend * Decimal(step))
            uncertainty = spread * Decimal(step).sqrt()
            lower = max(ZERO, expected - uncertainty)
            upper = expected + uncertainty
            daily_forecast.append(
                DailyForecast(
                    date=query.end_date + timedelta(days=step),
                    actual_cost=None,
                    forecast_cost=_quantize(expected),
                    lower_bound=_quantize(lower),
                    upper_bound=_quantize(upper),
                )
            )
        comparable = [value for _, value in daily[-query.horizon_days :]]
        historical_cost = sum(comparable, ZERO)
        projected = sum((point.forecast_cost for point in daily_forecast), ZERO)
        lower_total = sum((point.lower_bound for point in daily_forecast), ZERO)
        upper_total = sum((point.upper_bound for point in daily_forecast), ZERO)
        source = records[0] if records else None
        payload = (
            f"{self._user_scope}|{query.model_dump_json()}|{key}|{METHODOLOGY_VERSION}"
        )
        return ForecastResult(
            forecast_id=hashlib.sha256(payload.encode()).hexdigest()[:24],
            dimension=query.dimension,
            dimension_value=key,
            provider=(
                key if query.dimension is ForecastDimension.PROVIDER else query.provider
            ),
            account_id=query.account_id,
            service=(
                key if query.dimension is ForecastDimension.SERVICE else query.service
            ),
            region=key if query.dimension is ForecastDimension.REGION else query.region,
            forecast_start=forecast_start,
            forecast_end=forecast_start + timedelta(days=query.horizon_days - 1),
            horizon_days=query.horizon_days,
            currency=source.currency if source else "USD",
            historical_cost=_quantize(historical_cost),
            projected_cost=_quantize(projected),
            daily_forecast=daily_forecast,
            historical_daily=[
                DailyActual(date=day, cost=_quantize(value)) for day, value in daily
            ],
            lower_bound=_quantize(lower_total),
            upper_bound=_quantize(upper_total),
            methodology=(
                "Weighted seven-day level with bounded linear trend; robust "
                "median/MAD outlier exclusion."
            ),
            confidence=confidence,
            data_points_used=len(values),
            generated_at=datetime.now(UTC),
            excluded_anomaly_dates=excluded,
            missing_dates=missing,
        )

    async def forecast(self, query: ForecastQuery) -> ForecastResponse:
        cache_key = self._cache_key(query)
        if self._cache is not None:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                try:
                    return ForecastResponse.model_validate(cached)
                except Exception:
                    logger.warning("forecast_cache_invalid")
        records = _filter_records(
            await self._explorer.get_cost_records(
                query.start_date, query.end_date, query.provider
            ),
            query,
        )
        records, duplicate_count = _unique_records(records)
        if not records:
            quality = ForecastDataQuality(
                available_observations=0,
                required_observations=MIN_OBSERVATIONS,
                duplicate_records_removed=duplicate_count,
                warnings=["No normalized cost records matched the filters."],
            )
            return self._empty_response(
                query,
                quality,
                "Forecast unavailable because no cost data matched the filters.",
            )
        currencies = {record.currency for record in records}
        warnings: list[str] = []
        if len(currencies) > 1:
            warnings.append(
                "Multiple currencies were found; forecast results are separated "
                "by the first record currency."
            )
        grouped = _group_records(records, query.dimension)
        results: list[ForecastResult] = []
        all_missing: list[date] = []
        all_excluded: list[date] = []
        for key, group in sorted(grouped.items()):
            daily, missing = _daily_values(group, query.start_date, query.end_date)
            all_missing.extend(missing)
            result = self._forecast_group(key, group, query, missing)
            if result:
                results.append(result)
                all_excluded.extend(result.excluded_anomaly_dates)
        all_daily, all_missing = _daily_values(
            records, query.start_date, query.end_date
        )
        quality = ForecastDataQuality(
            available_observations=len(all_daily) - len(all_missing),
            required_observations=MIN_OBSERVATIONS,
            missing_dates=sorted(set(all_missing)),
            duplicate_records_removed=duplicate_count,
            excluded_anomaly_dates=sorted(set(all_excluded)),
            warnings=warnings,
        )
        if not results:
            return self._empty_response(
                query,
                quality,
                f"At least {MIN_OBSERVATIONS} daily observations are required "
                "for a reliable forecast.",
            )
        projected = sum((result.projected_cost for result in results), ZERO)
        historical = sum((result.historical_cost for result in results), ZERO)
        days = max((query.end_date - query.start_date).days + 1, 1)
        average = _quantize(
            sum((record.cost for record in records), ZERO) / Decimal(days)
        )
        change = (
            _quantize((projected - historical) / historical * Decimal("100"))
            if historical
            else None
        )
        summary = ForecastSummary(
            current_spend=_quantize(historical),
            projected_spend=_quantize(projected),
            projected_change_percentage=change,
            average_historical_daily_cost=average,
            projected_daily_average=_quantize(projected / Decimal(query.horizon_days)),
            confidence=min(
                (result.confidence for result in results),
                key={"low": 0, "medium": 1, "high": 2}.get,
            ),
            data_points_used=sum(result.data_points_used for result in results),
        )
        response = ForecastResponse(
            status=ForecastStatus.READY,
            query=query,
            summary=summary,
            forecasts=results,
            data_quality=quality,
            methodology_version=METHODOLOGY_VERSION,
        )
        if self._cache is not None:
            await self._cache.set_json(cache_key, response, 3600)
        return response

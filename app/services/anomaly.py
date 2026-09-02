"""Deterministic, provider-independent cost anomaly detection."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from app.core.cache import RedisCache
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.anomaly import (
    Anomaly,
    AnomalyQuery,
    AnomalyResponse,
    AnomalySeverity,
    AnomalySummary,
    AnomalyTrendPoint,
    DetectionMethod,
)
from app.schemas.explorer import CostRecord
from app.services.explorer.service import CostExplorerService

DETECTOR_VERSION = "1.0"
CENT = Decimal("0.01")
SCALE = Decimal("1.4826")
MIN_SCALE = Decimal("0.01")
logger = get_logger(__name__)


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def median_mad(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Return robust median and median absolute deviation for a series."""
    if not values:
        raise ValueError("at least one value is required")
    center = median(values)
    mad = median([abs(value - center) for value in values])
    return Decimal(str(center)), Decimal(str(mad))


class AnomalyDetectionService:
    """Find significant daily deviations using a configurable median/MAD baseline."""

    def __init__(
        self,
        explorer: CostExplorerService | None = None,
        cache: RedisCache | None = None,
        user_scope: str = "shared",
    ) -> None:
        self._explorer = explorer or CostExplorerService(
            cache=cache, user_scope=user_scope
        )
        self._cache = cache
        self._user_scope = user_scope

    def _cache_key(self, query: AnomalyQuery) -> str:
        config = {
            "version": DETECTOR_VERSION,
            "lookback": settings.anomaly_lookback_days,
            "min_history": settings.anomaly_min_history_points,
            "min_cost": str(settings.anomaly_min_cost),
            "min_pct": str(settings.anomaly_min_deviation_percentage),
            "scores": [
                str(settings.anomaly_low_score),
                str(settings.anomaly_medium_score),
                str(settings.anomaly_high_score),
                str(settings.anomaly_critical_score),
            ],
        }
        payload = f"{self._user_scope}|{query.model_dump_json()}|{config}"
        digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
        return f"anomaly:{self._user_scope}:{DETECTOR_VERSION}:{digest}"

    @staticmethod
    def _dimension(record: CostRecord) -> tuple[str, str | None, str, str | None]:
        return (
            record.provider.lower(),
            record.account_id,
            record.service,
            record.region,
        )

    @staticmethod
    def _matches(record: CostRecord, query: AnomalyQuery) -> bool:
        return (
            (not query.provider or record.provider.lower() == query.provider.lower())
            and (
                not query.account_id
                or (
                    record.account_id
                    and query.account_id.lower() in record.account_id.lower()
                )
            )
            and (not query.service or query.service.lower() in record.service.lower())
            and (
                not query.region
                or (record.region and query.region.lower() in record.region.lower())
            )
        )

    def _severity(self, score: Decimal) -> AnomalySeverity:
        if score >= settings.anomaly_critical_score:
            return AnomalySeverity.CRITICAL
        if score >= settings.anomaly_high_score:
            return AnomalySeverity.HIGH
        if score >= settings.anomaly_medium_score:
            return AnomalySeverity.MEDIUM
        if score >= settings.anomaly_low_score:
            return AnomalySeverity.LOW
        return AnomalySeverity.NORMAL

    async def detect(self, query: AnomalyQuery) -> AnomalyResponse:
        if self._cache is not None:
            cached = await self._cache.get_json(self._cache_key(query))
            if cached is not None:
                try:
                    return AnomalyResponse.model_validate(cached)
                except Exception:
                    logger.warning("anomaly_cache_invalid")

        history_start = query.start_date - timedelta(
            days=settings.anomaly_lookback_days
        )
        records = await self._explorer.get_cost_records(
            history_start, query.end_date, query.provider
        )

        # Deduplicate provider line items before calculating any baseline.
        unique: dict[tuple[object, ...], CostRecord] = {}
        for record in records:
            if not self._matches(record, query):
                continue
            key = (record.date, *self._dimension(record), record.cost, record.currency)
            unique[key] = record

        by_dimension_day: defaultdict[
            tuple[tuple[str, str | None, str, str | None], str],
            defaultdict[date, Decimal],
        ] = defaultdict(lambda: defaultdict(Decimal))
        metadata: dict[tuple[str, str | None, str, str | None], CostRecord] = {}
        for record in unique.values():
            dimension = self._dimension(record)
            by_dimension_day[(dimension, record.currency)][record.date] += record.cost
            metadata.setdefault((dimension, record.currency), record)

        now = datetime.now(UTC)
        found: list[Anomaly] = []
        for (dimension, currency), daily in by_dimension_day.items():
            history = [daily[d] for d in daily if history_start <= d < query.start_date]
            if len(history) < settings.anomaly_min_history_points:
                continue
            center, mad = median_mad(history)
            record_meta = metadata[(dimension, currency)]
            for day in sorted(
                d for d in daily if query.start_date <= d <= query.end_date
            ):
                actual = daily[day]
                deviation = actual - center
                if deviation <= 0 or deviation < settings.anomaly_min_cost:
                    continue
                if center > 0:
                    percentage = _money((deviation / center) * 100)
                    if percentage < settings.anomaly_min_deviation_percentage:
                        continue
                    scale = max(SCALE * mad, MIN_SCALE)
                    score = _money(abs(deviation) / scale)
                    method = DetectionMethod.MEDIAN_MAD
                else:
                    # A zero baseline is meaningful only when history is sufficient;
                    # use a bounded, explicit score instead of manufacturing a percent.
                    percentage = None
                    score = settings.anomaly_critical_score
                    method = DetectionMethod.ZERO_BASELINE
                severity = self._severity(score)
                if severity is AnomalySeverity.NORMAL:
                    continue
                identity = (
                    f"{day}|{dimension}|{currency}|{actual}|{center}|{DETECTOR_VERSION}"
                )
                found.append(
                    Anomaly(
                        id=hashlib.sha256(identity.encode()).hexdigest()[:20],
                        provider=record_meta.provider.lower(),
                        account_id=record_meta.account_id,
                        account_name=record_meta.account_name,
                        service=record_meta.service,
                        region=record_meta.region,
                        date=day,
                        actual_cost=_money(actual),
                        expected_cost=_money(center),
                        deviation_amount=_money(deviation),
                        deviation_percentage=percentage,
                        anomaly_score=score,
                        severity=severity,
                        detection_method=method,
                        baseline_period=(
                            f"{history_start.isoformat()}:"
                            f"{(query.start_date - timedelta(days=1)).isoformat()}"
                        ),
                        currency=currency,
                        created_at=now,
                    )
                )

        reverse = query.sort_order == "desc"
        found.sort(
            key=lambda item: (getattr(item, query.sort_by) or Decimal("-1"), item.id),
            reverse=reverse,
        )
        if query.severity:
            found = [item for item in found if item.severity is query.severity]
        total = len(found)
        summary = AnomalySummary(
            total=total,
            high_or_critical=sum(
                item.severity in {AnomalySeverity.HIGH, AnomalySeverity.CRITICAL}
                for item in found
            ),
            by_severity={
                severity: sum(item.severity is severity for item in found)
                for severity in AnomalySeverity
            },
        )
        response = AnomalyResponse(
            anomalies=found[query.offset : query.offset + query.limit],
            total=total,
            limit=query.limit,
            offset=query.offset,
            summary=summary,
            trend=[
                AnomalyTrendPoint(
                    date=day,
                    count=sum(item.date == day for item in found),
                )
                for day in sorted({item.date for item in found})
            ],
            start_date=query.start_date,
            end_date=query.end_date,
            baseline_lookback_days=settings.anomaly_lookback_days,
            detector_version=DETECTOR_VERSION,
        )
        if self._cache is not None:
            await self._cache.set_json(
                self._cache_key(query), response, settings.anomaly_cache_ttl_seconds
            )
        return response

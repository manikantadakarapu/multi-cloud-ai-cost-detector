"""Build deterministic, provider-neutral evidence for one cost anomaly."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from app.schemas.anomaly import Anomaly
from app.schemas.anomaly_explanation import (
    AnomalyInvestigationContext,
    BreakdownEvidence,
    DailyEvidence,
    EvidenceItem,
    EvidenceStatus,
)
from app.schemas.explorer import CostRecord

CONTEXT_VERSION = "1.0"
CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _percentage(change: Decimal, baseline: Decimal) -> Decimal | None:
    if baseline <= 0:
        return None
    return _money(change / baseline * 100)


def _same_dimension(record: CostRecord, anomaly: Anomaly) -> bool:
    return (
        record.provider.lower() == anomaly.provider.lower()
        and record.account_id == anomaly.account_id
        and record.service == anomaly.service
        and record.region == anomaly.region
        and record.currency == anomaly.currency
    )


def _breakdowns(
    records: list[CostRecord],
    anomaly: Anomaly,
    dimension: str,
    match_fields: tuple[str, ...],
) -> list[BreakdownEvidence]:
    baseline_start = date.fromisoformat(anomaly.baseline_period.split(":", 1)[0])
    baseline_end = anomaly.date - timedelta(days=1)
    current: defaultdict[str, Decimal] = defaultdict(Decimal)
    historical: defaultdict[str, list[Decimal]] = defaultdict(list)
    for record in records:
        if record.currency != anomaly.currency:
            continue
        if any(
            getattr(record, field) != getattr(anomaly, field) for field in match_fields
        ):
            continue
        value = getattr(record, dimension) or "unknown"
        if record.date == anomaly.date:
            current[value] += record.cost
        elif baseline_start <= record.date <= baseline_end:
            historical[value].append(record.cost)

    increment = sum(current.values(), Decimal("0")) - sum(
        (_money(median(values)) for values in historical.values() if values),
        Decimal("0"),
    )
    result: list[BreakdownEvidence] = []
    for value, current_cost in current.items():
        baseline_cost = (
            _money(median(historical[value])) if historical.get(value) else Decimal("0")
        )
        change = _money(current_cost - baseline_cost)
        result.append(
            BreakdownEvidence(
                dimension=dimension,
                value=value,
                current_cost=_money(current_cost),
                baseline_cost=baseline_cost,
                change_amount=change,
                change_percentage=_percentage(change, baseline_cost),
                share_of_increment=(
                    _money(change / increment * 100)
                    if increment > 0 and change > 0
                    else None
                ),
            )
        )
    result.sort(key=lambda item: (item.change_amount, item.value), reverse=True)
    return result[:10]


def build_anomaly_context(
    anomaly: Anomaly, records: list[CostRecord]
) -> AnomalyInvestigationContext:
    """Derive explainable evidence without calling an AI or provider SDK."""
    daily: defaultdict[date, Decimal] = defaultdict(Decimal)
    matched = [record for record in records if _same_dimension(record, anomaly)]
    for record in matched:
        daily[record.date] += record.cost

    evidence = [
        EvidenceItem(
            label="Actual cost",
            value=f"{anomaly.actual_cost} {anomaly.currency}",
            status=EvidenceStatus.VERIFIED,
        ),
        EvidenceItem(
            label="Expected cost",
            value=f"{anomaly.expected_cost} {anomaly.currency}",
            status=EvidenceStatus.VERIFIED,
        ),
        EvidenceItem(
            label="Deviation",
            value=f"{anomaly.deviation_amount} {anomaly.currency}",
            status=EvidenceStatus.VERIFIED,
        ),
        EvidenceItem(
            label="Deviation percentage",
            value=(
                f"{anomaly.deviation_percentage}%"
                if anomaly.deviation_percentage is not None
                else "UNKNOWN"
            ),
            status=(
                EvidenceStatus.VERIFIED
                if anomaly.deviation_percentage is not None
                else EvidenceStatus.UNKNOWN
            ),
        ),
        EvidenceItem(
            label="Anomaly score",
            value=str(anomaly.anomaly_score),
            status=EvidenceStatus.VERIFIED,
        ),
        EvidenceItem(
            label="Severity",
            value=anomaly.severity.value,
            status=EvidenceStatus.VERIFIED,
        ),
        EvidenceItem(
            label="Baseline period",
            value=anomaly.baseline_period,
            status=EvidenceStatus.VERIFIED,
        ),
    ]
    if anomaly.expected_cost > 0:
        evidence.append(
            EvidenceItem(
                label="Actual-to-baseline ratio",
                value=f"{_money(anomaly.actual_cost / anomaly.expected_cost)}x",
                status=EvidenceStatus.DERIVED,
            )
        )

    daily_values = [
        DailyEvidence(date=day, cost=_money(daily[day])) for day in sorted(daily)
    ]
    unknowns: list[str] = []
    if not matched:
        unknowns.append(
            "No normalized line-item records were available for this anomaly dimension."
        )
    if not anomaly.region:
        unknowns.append("The anomaly has no region dimension.")
    if not anomaly.account_id:
        unknowns.append(
            "The anomaly has no account, project, or subscription dimension."
        )

    return AnomalyInvestigationContext(
        context_version=CONTEXT_VERSION,
        anomaly=anomaly,
        evidence=evidence,
        daily_costs=daily_values[-14:],
        service_changes=_breakdowns(
            records, anomaly, "service", ("provider", "account_id", "region")
        ),
        region_changes=_breakdowns(
            records, anomaly, "region", ("provider", "account_id", "service")
        ),
        provider_changes=_breakdowns(
            records, anomaly, "provider", ("account_id", "service", "region")
        ),
        unknowns=unknowns,
    )

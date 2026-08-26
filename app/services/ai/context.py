"""Build a facts-only Gemini context from a deterministic cost event."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.cost_events import CostEvent, CostEventType

SYSTEM_PROMPT = (
    "You explain one deterministic cloud cost change for a FinOps dashboard.\n"
    "\n"
    "The user message is JSON containing measured billing facts. "
    "Those facts are the only evidence you may use.\n"
    "\n"
    "You must:\n"
    "- Explain the supplied cost event in concise professional language.\n"
    "- Restate only numbers that appear in the JSON. "
    "Never invent a new amount, percentage, or currency figure.\n"
    "- If the JSON does not identify a root cause, say that the cause "
    "cannot be determined from the available cost data.\n"
    "- Recommend a cautious human review step. Do not instruct anyone to "
    "delete, stop, resize, or modify cloud resources automatically.\n"
    "\n"
    "You must not invent:\n"
    "- cloud resources, instance types, SKUs, or resource IDs\n"
    "- usage quantities, regions, or availability zones\n"
    "- root causes, incidents, deployments, or owners\n"
    "- savings estimates or unused-capacity claims\n"
    "- metrics or billing line items that are not in the JSON\n"
    "- credentials, tokens, environment variables, or internal identifiers\n"
    "\n"
    "Return JSON only with these keys:\n"
    "- title: short headline\n"
    "- summary: one or two sentences that restate the measured change\n"
    "- severity: low, medium, or high\n"
    "- likely_cause: what can and cannot be concluded from the supplied "
    "cost data\n"
    "- recommended_action: a review action for a human, not an automated "
    "change\n"
    "\n"
    "Do not wrap the JSON in markdown."
)


class AIInsightContext(BaseModel):
    """Facts-only payload sent to Gemini. Contains no secrets or SDK objects."""

    model_config = ConfigDict(extra="forbid")

    event_type: CostEventType
    provider: str | None = None
    service: str | None = None
    current_cost: Decimal
    previous_cost: Decimal
    absolute_change: Decimal
    percentage_change: Decimal | None = None
    currency: str
    period_start: str
    period_end: str
    cause_is_unknown: bool = True


def build_ai_context(event: CostEvent) -> AIInsightContext:
    """Convert a cost event into the constrained model input."""
    return AIInsightContext(
        event_type=event.event_type,
        provider=event.provider,
        service=event.service,
        current_cost=event.current_cost,
        previous_cost=event.previous_cost,
        absolute_change=event.absolute_change,
        percentage_change=event.percentage_change,
        currency=event.currency,
        period_start=event.period_start.isoformat(),
        period_end=event.period_end.isoformat(),
        cause_is_unknown=True,
    )


def build_user_prompt(context: AIInsightContext) -> str:
    """Serialize the facts-only context for the Gemini user turn."""
    return context.model_dump_json()


def deterministic_summary(event: CostEvent) -> str:
    """Human-readable change summary whose numbers come only from analytics."""
    subject = event.service or event.provider or "Cloud spending"
    direction = (
        "increased" if event.event_type == CostEventType.COST_INCREASE else "decreased"
    )
    rate = (
        f" by {abs(event.percentage_change):.2f}%"
        if event.percentage_change is not None
        else ""
    )
    return (
        f"{subject} costs {direction}{rate}, a change of "
        f"{abs(event.absolute_change):.2f} {event.currency} compared with the previous period."
    )


def deterministic_title(event: CostEvent) -> str:
    """Fallback title used when Gemini output is unusable."""
    subject = event.service or event.provider or "Cloud spending"
    if event.event_type == CostEventType.COST_INCREASE:
        return f"{subject} spending increased significantly"
    return f"{subject} spending decreased significantly"

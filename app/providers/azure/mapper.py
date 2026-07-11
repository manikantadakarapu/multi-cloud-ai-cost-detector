"""Mapper from raw Azure Cost Management responses to provider-agnostic schemas.

:class:`AzureMapper` is a stateless adapter that turns the normalized dict
returned by :class:`app.services.azure.cost_management.AzureCostManagementService`
into the :class:`app.providers.schemas.CostResponse` model that the rest of
the application consumes. Keeping this translation in its own class makes
the mapping logic easy to unit test in isolation from the Azure SDK.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.providers.schemas import CostResponse, ServiceCost


class AzureMapper:
    """Translate Azure-specific dicts into :class:`CostResponse`."""

    def map(
        self,
        raw: dict[str, Any],
        start_date: date,
        end_date: date,
        granularity: str,
    ) -> CostResponse:
        """Convert a raw Azure cost dict into a :class:`CostResponse`.

        The ``raw`` dict is the normalized structure produced by
        :meth:`app.services.azure.cost_management.AzureCostManagementService.get_costs`
        with keys ``provider``, ``currency``, ``total_cost``, ``services``
        and ``date_range``. Missing ``date_range`` or ``services`` keys
        are filled in defensively so callers do not have to special-case
        partial responses.
        """
        date_range = raw.get("date_range")
        if not isinstance(date_range, dict) or not date_range:
            date_range = {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "granularity": granularity,
            }

        services_raw = raw.get("services") or []
        services = [
            ServiceCost(
                service_name=str(item["service_name"]),
                cost=float(item["cost"]),
            )
            for item in services_raw
        ]

        return CostResponse(
            provider=str(raw.get("provider", "azure")),
            currency=str(raw.get("currency", "USD")),
            total_cost=float(raw.get("total_cost", 0.0)),
            date_range={
                "start": str(date_range.get("start", start_date.isoformat())),
                "end": str(date_range.get("end", end_date.isoformat())),
                "granularity": str(date_range.get("granularity", granularity)),
            },
            services=services,
        )

"""Tests for Azure Cost Management Pydantic schemas."""

from __future__ import annotations

from datetime import date

import pytest

from app.schemas.azure import AzureCostRequest


class TestAzureCostRequest:
    def test_valid_request(self):
        """Valid request with all fields parses correctly."""
        req = AzureCostRequest(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            granularity="DAILY",
        )
        assert req.start_date == date(2024, 1, 1)
        assert req.end_date == date(2024, 1, 31)
        assert req.granularity == "DAILY"

    def test_default_granularity_is_daily(self):
        """Default granularity is DAILY when not provided."""
        req = AzureCostRequest(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        assert req.granularity == "DAILY"

    def test_invalid_granularity(self):
        """Invalid granularity raises validation error."""
        with pytest.raises(ValueError):
            AzureCostRequest(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="HOURLY",
            )

    def test_end_before_start(self):
        """end_date before start_date raises validation error."""
        with pytest.raises(ValueError):
            AzureCostRequest(
                start_date=date(2024, 1, 31),
                end_date=date(2024, 1, 1),
                granularity="DAILY",
            )

"""Tests for AWS Cost Explorer Pydantic schemas."""

from __future__ import annotations

from datetime import date

import pytest

from app.schemas.aws import AWSCostRequest, AWSCostResponse, AWSServiceCost


class TestAWSCostRequest:
    def test_valid_request(self):
        """Valid request with all fields."""
        req = AWSCostRequest(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            granularity="DAILY",
        )
        assert req.start_date == date(2024, 1, 1)
        assert req.end_date == date(2024, 1, 31)
        assert req.granularity == "DAILY"

    def test_invalid_granularity(self):
        """Invalid granularity raises validation error."""
        with pytest.raises(ValueError):
            AWSCostRequest(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                granularity="HOURLY",
            )

    def test_end_before_start(self):
        """end_date before start_date raises validation error."""
        with pytest.raises(ValueError):
            AWSCostRequest(
                start_date=date(2024, 1, 31),
                end_date=date(2024, 1, 1),
                granularity="DAILY",
            )


class TestAWSCostResponse:
    def test_valid_response(self):
        """Valid response structure."""
        resp = AWSCostResponse(
            provider="aws",
            currency="USD",
            total_cost=150.75,
            date_range={
                "start": "2024-01-01",
                "end": "2024-01-31",
                "granularity": "DAILY",
            },
            services=[
                AWSServiceCost(service_name="AmazonEC2", cost=100.50),
                AWSServiceCost(service_name="AmazonS3", cost=50.25),
            ],
        )
        assert resp.provider == "aws"
        assert resp.total_cost == 150.75
        assert len(resp.services) == 2


class TestAWSServiceCost:
    def test_negative_cost_rejected(self):
        """Negative cost values are rejected."""
        with pytest.raises(ValueError):
            AWSServiceCost(service_name="AmazonEC2", cost=-10.0)

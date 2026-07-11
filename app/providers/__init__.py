"""Cloud provider abstraction package.

This package exposes a provider-agnostic interface for integrating with
multiple cloud providers (AWS, GCP, Azure, etc.). It provides:

* A typed :class:`CloudProvider` ABC that all provider implementations
  must satisfy.
* Normalized response schemas (:class:`CostResponse`, :class:`ServiceCost`)
  so the rest of the application can work with a uniform shape
  regardless of the underlying vendor.
* A provider-agnostic :class:`ProviderError` exception hierarchy.
* A manual registry (:func:`register_provider` / :func:`get_provider`)
  used to look up concrete provider implementations by name.
"""

from __future__ import annotations

from app.providers import aws as _aws_provider  # noqa: F401 -- registers "aws" factory
from app.providers import (
    azure as _azure_provider,  # noqa: F401 -- registers "azure" factory
)
from app.providers.base import CloudProvider
from app.providers.exceptions import (
    ProviderCredentialsError,
    ProviderError,
    ProviderInvalidDateRangeError,
    ProviderPermissionsError,
    ProviderServiceError,
    ProviderThrottlingError,
)
from app.providers.registry import (
    PROVIDER_REGISTRY,
    get_provider,
    get_provider_factory,
    list_providers,
    register_provider,
)
from app.providers.schemas import CostResponse, ServiceCost

__all__ = [
    "CloudProvider",
    "CostResponse",
    "ServiceCost",
    "ProviderError",
    "ProviderCredentialsError",
    "ProviderInvalidDateRangeError",
    "ProviderPermissionsError",
    "ProviderServiceError",
    "ProviderThrottlingError",
    "PROVIDER_REGISTRY",
    "register_provider",
    "get_provider",
    "get_provider_factory",
    "list_providers",
]

"""Azure cloud provider package.

Exports the :class:`AzureCloudProvider` implementation and its
:class:`AzureMapper`, and registers a factory for the ``"azure"`` key in
:data:`app.providers.registry.PROVIDER_REGISTRY` so that
:func:`app.providers.registry.get_provider` resolves it at import
time.
"""

from __future__ import annotations

from app.providers.azure.mapper import AzureMapper
from app.providers.azure.provider import AzureCloudProvider
from app.providers.registry import register_provider

register_provider("azure", lambda: AzureCloudProvider())

__all__ = ["AzureCloudProvider", "AzureMapper"]

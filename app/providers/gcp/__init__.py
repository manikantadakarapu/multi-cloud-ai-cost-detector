"""GCP cloud provider package.

Exports the :class:`GCPCloudProvider` implementation and its
:class:`GCPMapper`, and registers a factory for the ``"gcp"`` key in
:data:`app.providers.registry.PROVIDER_REGISTRY` so that
:func:`app.providers.registry.get_provider` resolves it at import
time.
"""

from __future__ import annotations

from app.providers.gcp.mapper import GCPMapper
from app.providers.gcp.provider import GCPCloudProvider
from app.providers.registry import register_provider

register_provider("gcp", lambda: GCPCloudProvider())

__all__ = ["GCPCloudProvider", "GCPMapper"]

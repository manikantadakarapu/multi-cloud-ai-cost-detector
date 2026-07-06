"""AWS cloud provider package.

Exports the :class:`AWSCloudProvider` implementation and its
:class:`AWSMapper`, and registers a factory for the ``"aws"`` key in
:data:`app.providers.registry.PROVIDER_REGISTRY` so that
:func:`app.providers.registry.get_provider` resolves it at import
time.
"""

from __future__ import annotations

from app.providers.aws.mapper import AWSMapper
from app.providers.aws.provider import AWSCloudProvider
from app.providers.registry import register_provider

register_provider("aws", lambda: AWSCloudProvider())

__all__ = ["AWSCloudProvider", "AWSMapper"]

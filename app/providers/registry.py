"""Manual cloud-provider registry.

Concrete providers register a zero-argument factory by name at import
time; FastAPI routes resolve a factory via :func:`get_provider` and
inject a fresh instance per request. This keeps the registry free of
any external dependency-injection libraries.
"""

from __future__ import annotations

from collections.abc import Callable

from app.providers.base import CloudProvider
from app.providers.exceptions import ProviderError

PROVIDER_REGISTRY: dict[str, Callable[[], CloudProvider]] = {}


def register_provider(name: str, factory: Callable[[], CloudProvider]) -> None:
    """Register ``factory`` under ``name``.

    If a factory is already registered under ``name`` it is overwritten;
    this is intentional so tests and tooling can replace entries
    without restarting the process.
    """
    PROVIDER_REGISTRY[name] = factory


def get_provider_factory(name: str) -> Callable[[], CloudProvider]:
    """Return the registered factory for ``name``.

    Raises :class:`ProviderError` when no factory is registered under
    ``name``. The returned callable takes no arguments and returns a
    fresh :class:`CloudProvider` instance on each call.
    """
    factory = PROVIDER_REGISTRY.get(name)
    if factory is None:
        raise ProviderError(
            f"Cloud provider '{name}' is not registered",
            error_code="PROVIDER_NOT_REGISTERED",
        )
    return factory


def get_provider(name: str) -> Callable[[], CloudProvider]:
    """Return a ``Depends``-compatible callable for ``name``.

    The returned callable, when invoked with no arguments, builds and
    returns a fresh :class:`CloudProvider` instance via the registered
    factory. Use it with ``fastapi.Depends``:

        service: Annotated[CloudProvider, Depends(get_provider("aws"))]

    Raises :class:`ProviderError` at registration-resolution time when
    no factory is registered under ``name``.
    """
    return get_provider_factory(name)


def list_providers() -> list[str]:
    """Return the names of all registered cloud-provider factories."""
    return list(PROVIDER_REGISTRY.keys())

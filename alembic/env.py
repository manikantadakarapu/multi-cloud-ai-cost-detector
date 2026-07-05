from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from urllib.parse import urlparse

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ensure the project root is on sys.path so `app.*` imports resolve when
# alembic is invoked from any working directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Import all models so Alembic autogenerate discovers them.
# The auth package ``__init__`` currently imports service/dependency modules
# that reference removed model members, so we load ``app.auth.models``
# directly to avoid executing the package ``__init__`` during migrations.
import importlib.util  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.database.base import Base  # noqa: E402

_auth_models_path = (
    Path(__file__).resolve().parent.parent / "app" / "auth" / "models.py"
)
_spec = importlib.util.spec_from_file_location("app.auth.models", _auth_models_path)
_auth_models = importlib.util.module_from_spec(_spec)
sys.modules["app.auth.models"] = _auth_models
_spec.loader.exec_module(_auth_models)  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def _mask_url(url: str) -> str:
    """Return the URL with the password replaced by *** for safe logging."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "<unparseable DATABASE_URL>"
    if parsed.password is None:
        return url
    user = parsed.username or ""
    netloc = f"{user}:***@{parsed.hostname or ''}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


# Surface the actual URL Alembic is using. This is the single most useful
# piece of evidence when auth fails: it tells you whether .env, the
# process environment, or a default value is the active source.
print(f"[alembic] DATABASE_URL = {_mask_url(settings.database_url)}", file=sys.stderr)
print(
    f"[alembic] driver        = {settings.database_url.split('://', 1)[0]}",
    file=sys.stderr,
)
print(
    f"[alembic] .env loaded?  = {settings.model_config.get('env_file')!r}",
    file=sys.stderr,
)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())

"""Database connectivity diagnostic.

Run this when ``alembic revision --autogenerate`` fails with
``asyncpg.exceptions.InvalidPasswordError`` (or any other auth error).
It prints exactly which URL is in effect and where it came from, then
attempts a real connection so you can see whether the problem is the
application, the .env file, or the PostgreSQL server itself.

Usage::

    python scripts/check_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


def _mask(url: str) -> str:
    try:
        p = urlparse(url)
    except Exception:
        return "<unparseable>"
    if p.password is None:
        return url
    user = p.username or ""
    netloc = f"{user}:***@{p.hostname or ''}"
    if p.port:
        netloc += f":{p.port}"
    return p._replace(netloc=netloc).geturl()


def _report_source() -> tuple[str, str]:
    """Return (source, value) for DATABASE_URL, in priority order."""
    if "DATABASE_URL" in os.environ:
        return "process env", os.environ["DATABASE_URL"]
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL"):
                _, _, value = line.partition("=")
                return ".env file", value.strip().strip('"').strip("'")
    return "default", "postgresql+asyncpg://mcaicd:mcaicd@localhost:5432/mcaicd"


def _to_asyncpg_dsn(url: str) -> str:
    """Strip SQLAlchemy's ``+asyncpg`` driver suffix so asyncpg accepts the URL."""
    parsed = urlparse(url)
    if "+" in parsed.scheme:
        parsed = parsed._replace(scheme=parsed.scheme.split("+", 1)[0])
    return parsed.geturl()


async def _probe(url: str) -> tuple[bool, str]:
    try:
        import asyncpg  # local import so this script can run without the full app deps
    except ImportError:
        return False, "asyncpg is not installed in the current environment"

    try:
        conn = await asyncpg.connect(_to_asyncpg_dsn(url), timeout=5)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    user = await conn.fetchval("SELECT current_user")
    db = await conn.fetchval("SELECT current_database()")
    server = await conn.fetchval("SHOW server_version")
    await conn.close()
    return True, f"connected as {user!r} to db {db!r} (server {server})"


async def main() -> int:
    source, raw = _report_source()
    print("== Database connectivity check ==")
    print(f"DATABASE_URL source : {source}")
    print(f"DATABASE_URL value  : {_mask(raw)}")

    parsed = urlparse(raw)
    scheme = parsed.scheme
    driver = scheme.split("+", 1)[1] if "+" in scheme else "(none)"
    print(f"scheme              : {scheme}")
    print(f"driver              : {driver}")
    print(f"host:port           : {parsed.hostname}:{parsed.port}")
    print(f"database            : {parsed.path.lstrip('/')}")
    print(f"user                : {parsed.username}")
    print(f"password length     : {len(parsed.password) if parsed.password else 0}")

    if driver != "asyncpg":
        print(
            "\n[!] WARNING: SQLAlchemy 2.x async requires the 'postgresql+asyncpg://' "
            "scheme. You will get cryptic errors with sync drivers in an async context.",
        )

    print("\n== Attempting connection ==")
    ok, detail = await _probe(raw)
    print(("OK  " if ok else "FAIL"), detail)

    if not ok:
        print(
            "\nCommon causes:\n"
            "  1. .env and PostgreSQL are out of sync. The password in PostgreSQL\n"
            "     must match the password in DATABASE_URL exactly. Reset with:\n"
            "         docker exec -it postgres-mcaicd psql -U mcaicd -d mcaicd \\\n"
            "           -c \"ALTER USER testuser WITH PASSWORD 'testuser123';\"\n"
            "  2. A stale DATABASE_URL in your shell or Windows system env vars is\n"
            "     overriding .env (pydantic-settings picks the env var first).\n"
            "     In PowerShell:  Remove-Item Env:DATABASE_URL\n"
            "  3. POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB env vars on the\n"
            "     container are only honored on first init. Changing them later\n"
            "     does NOT update the existing PostgreSQL user.\n"
            "  4. Port 5432 is mapped to a different container. Check with:\n"
            "         docker ps\n"
            "         docker inspect postgres-mcaicd --format '{{.NetworkSettings.Ports}}'\n",
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

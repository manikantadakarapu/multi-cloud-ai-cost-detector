"""Password hashing and verification utilities.

Uses :mod:`bcrypt` via its native API rather than passlib's bcrypt backend
to avoid the passlib/bcrypt version-incompatibility issues that surfaced in
recent releases.  The hash format is standard bcrypt (``$2b$...``) and
remains interchangeable with any bcrypt verifier.
"""

from __future__ import annotations

import bcrypt

from app.core.logging import get_logger

logger = get_logger(__name__)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt.

    The generated salt uses bcrypt's default work factor (12 rounds),
    providing a good balance between security and performance.

    Parameters
    ----------
    plain_password:
        The plaintext password to hash.

    Returns
    -------
    str
        The bcrypt hash string (``$2b$...``).
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Parameters
    ----------
    plain_password:
        The plaintext password to check.
    hashed_password:
        The stored bcrypt hash.

    Returns
    -------
    bool
        ``True`` if the password matches the hash, ``False`` otherwise.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        logger.warning(
            "password_verification_failed", extra={"reason": "invalid_hash_format"}
        )
        return False

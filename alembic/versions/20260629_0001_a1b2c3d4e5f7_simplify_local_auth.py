"""Simplify auth schema for local JWT only

Revision ID: a1b2c3d4e5f7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-29 00:01:00.000000+00:00

Drops:
  - ``revoked_tokens`` table: no longer needed for local JWT auth.
  - OAuth/RBAC columns from ``users``: ``auth_provider``, ``provider_user_id``,
    ``is_verified``, ``is_admin``.

Alters:
  - ``users.password_hash`` becomes non-nullable, matching the simplified
    local-only User model.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return inspector.has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def _in_offline_mode() -> bool:
    return context.is_offline_mode()


def upgrade() -> None:
    if _in_offline_mode() or _table_exists("revoked_tokens"):
        op.drop_index(op.f("ix_revoked_tokens_user_id"), table_name="revoked_tokens")
        op.drop_index(op.f("ix_revoked_tokens_jti"), table_name="revoked_tokens")
        op.drop_table("revoked_tokens")

    if _in_offline_mode() or _column_exists("users", "auth_provider"):
        op.drop_column("users", "auth_provider")
    if _in_offline_mode() or _column_exists("users", "provider_user_id"):
        op.drop_column("users", "provider_user_id")
    if _in_offline_mode() or _column_exists("users", "is_verified"):
        op.drop_column("users", "is_verified")
    if _in_offline_mode() or _column_exists("users", "is_admin"):
        op.drop_column("users", "is_admin")

    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(255),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(255),
        nullable=True,
    )

    if _in_offline_mode() or not _column_exists("users", "auth_provider"):
        op.add_column(
            "users",
            sa.Column(
                "auth_provider",
                sa.String(50),
                nullable=False,
                server_default="local",
            ),
        )
    if _in_offline_mode() or not _column_exists("users", "provider_user_id"):
        op.add_column(
            "users",
            sa.Column("provider_user_id", sa.String(255), nullable=True),
        )
    if _in_offline_mode() or not _column_exists("users", "is_verified"):
        op.add_column(
            "users",
            sa.Column(
                "is_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    if _in_offline_mode() or not _column_exists("users", "is_admin"):
        op.add_column(
            "users",
            sa.Column(
                "is_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    if _in_offline_mode() or not _table_exists("revoked_tokens"):
        op.create_table(
            "revoked_tokens",
            sa.Column("id", sa.Uuid, nullable=False),
            sa.Column("jti", sa.String(255), nullable=False),
            sa.Column("user_id", sa.Uuid, nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_revoked_tokens")),
            sa.UniqueConstraint("jti", name=op.f("uq_revoked_tokens_jti")),
        )
        op.create_index(
            op.f("ix_revoked_tokens_jti"),
            "revoked_tokens",
            ["jti"],
            unique=True,
        )
        op.create_index(
            op.f("ix_revoked_tokens_user_id"),
            "revoked_tokens",
            ["user_id"],
        )

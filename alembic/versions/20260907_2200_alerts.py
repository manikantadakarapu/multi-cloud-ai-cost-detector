"""create user-scoped cost alerts"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260907_2200"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("alert_type", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("account_id", sa.String(255), nullable=True),
        sa.Column("service", sa.String(255), nullable=True),
        sa.Column("region", sa.String(255), nullable=True),
        sa.Column("threshold", sa.Numeric(18, 4), nullable=True),
        sa.Column("percentage", sa.Numeric(9, 4), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "cooldown_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("360"),
        ),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index(op.f("ix_alerts_user_id"), "alerts", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_alerts_user_id"), table_name="alerts")
    op.drop_table("alerts")

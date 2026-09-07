"""create user-scoped cost budgets"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260908_2300"
down_revision: str | None = "20260907_2200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("user_id", sa.Uuid, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column(
            "scope", sa.String(32), nullable=False, server_default=sa.text("'total'")
        ),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("account_id", sa.String(255), nullable=True),
        sa.Column("service", sa.String(255), nullable=True),
        sa.Column("region", sa.String(255), nullable=True),
        sa.Column(
            "period", sa.String(16), nullable=False, server_default=sa.text("'monthly'")
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "currency", sa.String(3), nullable=False, server_default=sa.text("'USD'")
        ),
        sa.Column(
            "warning_threshold",
            sa.Numeric(7, 4),
            nullable=False,
            server_default=sa.text("80"),
        ),
        sa.Column(
            "critical_threshold",
            sa.Numeric(7, 4),
            nullable=False,
            server_default=sa.text("90"),
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
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
        sa.CheckConstraint("amount > 0", name="ck_budgets_amount_positive"),
        sa.CheckConstraint(
            "warning_threshold >= 0 AND warning_threshold <= 100",
            name="ck_budgets_warning_threshold_range",
        ),
        sa.CheckConstraint(
            "critical_threshold > warning_threshold AND critical_threshold <= 100",
            name="ck_budgets_critical_threshold_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
    )
    op.create_index(op.f("ix_budgets_user_id"), "budgets", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_budgets_user_id"), table_name="budgets")
    op.drop_table("budgets")

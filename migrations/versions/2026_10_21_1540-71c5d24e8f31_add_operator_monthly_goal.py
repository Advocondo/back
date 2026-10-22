"""add monthly goal to users

Revision ID: 71c5d24e8f31
Revises: a3c5e8d19b72
Create Date: 2026-10-21 15:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "71c5d24e8f31"
down_revision: str | Sequence[str] | None = "a3c5e8d19b72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "monthly_goal",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "monthly_goal")

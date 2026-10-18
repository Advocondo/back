"""add fee to agreements

Revision ID: 39cb57f92c5e
Revises: 4a5a3c0040a0
Create Date: 2026-10-17 15:15:27.250144

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "39cb57f92c5e"
down_revision: str | Sequence[str] | None = "4a5a3c0040a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Agreements registered before this change have no fee: they start at zero,
    # and the default is dropped so new agreements must always state their fee.
    op.add_column(
        "agreements",
        sa.Column(
            "fee_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("agreements", "fee_amount", server_default=None)
    op.add_column(
        "agreements",
        sa.Column("fee_percentage", sa.Numeric(precision=5, scale=2), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_agreements_fee_amount_within_total"),
        "agreements",
        "fee_amount >= 0 AND fee_amount <= total_amount",
    )
    op.create_check_constraint(
        op.f("ck_agreements_fee_percentage_within_range"),
        "agreements",
        "fee_percentage >= 0 AND fee_percentage <= 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_agreements_fee_percentage_within_range"), "agreements", type_="check"
    )
    op.drop_constraint(
        op.f("ck_agreements_fee_amount_within_total"), "agreements", type_="check"
    )
    op.drop_column("agreements", "fee_percentage")
    op.drop_column("agreements", "fee_amount")

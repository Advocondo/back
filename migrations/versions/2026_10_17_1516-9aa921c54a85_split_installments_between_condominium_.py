"""split installments between condominium and fee

Revision ID: 9aa921c54a85
Revises: 39cb57f92c5e
Create Date: 2026-10-17 15:16:47.068003

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9aa921c54a85"
down_revision: str | Sequence[str] | None = "39cb57f92c5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Installments created before this change go fully to the condominium (no fee);
    # the defaults are dropped so new installments must always state the split.
    op.add_column(
        "installments",
        sa.Column(
            "condominium_amount", sa.Numeric(precision=12, scale=2), nullable=True
        ),
    )
    op.add_column(
        "installments",
        sa.Column(
            "fee_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute("UPDATE installments SET condominium_amount = amount")
    op.alter_column("installments", "condominium_amount", nullable=False)
    op.alter_column("installments", "fee_amount", server_default=None)
    op.create_check_constraint(
        op.f("ck_installments_split_not_negative"),
        "installments",
        "condominium_amount >= 0 AND fee_amount >= 0",
    )
    op.create_check_constraint(
        op.f("ck_installments_split_adds_up_to_amount"),
        "installments",
        "condominium_amount + fee_amount = amount",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_installments_split_adds_up_to_amount"), "installments", type_="check"
    )
    op.drop_constraint(
        op.f("ck_installments_split_not_negative"), "installments", type_="check"
    )
    op.drop_column("installments", "fee_amount")
    op.drop_column("installments", "condominium_amount")

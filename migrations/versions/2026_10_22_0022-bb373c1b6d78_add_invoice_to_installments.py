"""add invoice to installments

Revision ID: bb373c1b6d78
Revises: 33fed27dfa21
Create Date: 2026-10-22 00:22:27.108711

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bb373c1b6d78"
down_revision: str | Sequence[str] | None = "33fed27dfa21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "installments", sa.Column("invoice_number", sa.String(length=15), nullable=True)
    )
    op.add_column("installments", sa.Column("invoice_date", sa.Date(), nullable=True))
    op.create_check_constraint(
        op.f("ck_installments_invoice_number_and_date_together"),
        "installments",
        "(invoice_number IS NULL) = (invoice_date IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_installments_invoice_number_and_date_together"),
        "installments",
        type_="check",
    )
    op.drop_column("installments", "invoice_date")
    op.drop_column("installments", "invoice_number")

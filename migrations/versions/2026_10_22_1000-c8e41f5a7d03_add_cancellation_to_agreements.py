"""add cancellation to agreements

Revision ID: c8e41f5a7d03
Revises: 79f61dbc2fd4
Create Date: 2026-10-22 10:00:12.314159

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e41f5a7d03"
down_revision: str | Sequence[str] | None = "79f61dbc2fd4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # O autogenerate não enxerga a mudança de uma CHECK, então ela é trocada à mão.
    op.drop_constraint(
        op.f("ck_agreements_agreement_status"), "agreements", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_agreements_agreement_status"),
        "agreements",
        "status IN ('active', 'cancelled')",
    )
    op.add_column(
        "agreements",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agreements",
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    # Falha, de propósito, se existir acordo cancelado: voltar a CHECK reativaria
    # esses acordos em silêncio. Quem precisar desfazer deve tratá-los antes.
    op.drop_column("agreements", "cancellation_reason")
    op.drop_column("agreements", "cancelled_at")
    op.drop_constraint(
        op.f("ck_agreements_agreement_status"), "agreements", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_agreements_agreement_status"),
        "agreements",
        "status IN ('active')",
    )

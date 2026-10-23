"""add partial payments to installments

Revision ID: 33fed27dfa21
Revises: 03141b30ed61
Create Date: 2026-10-21 21:51:32.050545

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "33fed27dfa21"
down_revision: str | Sequence[str] | None = "03141b30ed61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "installment_payments",
        sa.Column("installment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_installment_payments_amount_is_positive")
        ),
        sa.ForeignKeyConstraint(
            ["installment_id"],
            ["installments.id"],
            name=op.f("fk_installment_payments_installment_id_installments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_installment_payments")),
    )
    op.create_index(
        op.f("ix_installment_payments_installment_id"),
        "installment_payments",
        ["installment_id"],
        unique=False,
    )
    # Parcelas sem baixa começam sem nada pago; as já baixadas (US26) foram pagas
    # por inteiro, e o pagamento delas entra no histórico. O padrão é removido em
    # seguida, como na migration que dividiu as parcelas entre condomínio e
    # honorários.
    op.add_column(
        "installments",
        sa.Column(
            "paid_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        "UPDATE installments SET paid_amount = amount WHERE payment_date IS NOT NULL"
    )
    op.execute(
        "INSERT INTO installment_payments (installment_id, amount, payment_date) "
        "SELECT id, amount, payment_date FROM installments "
        "WHERE payment_date IS NOT NULL"
    )
    op.alter_column("installments", "paid_amount", server_default=None)
    op.create_check_constraint(
        op.f("ck_installments_paid_amount_within_amount"),
        "installments",
        "paid_amount >= 0 AND paid_amount <= amount",
    )
    op.create_check_constraint(
        op.f("ck_installments_paid_only_when_fully_paid"),
        "installments",
        "(payment_date IS NOT NULL) = (paid_amount = amount)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_installments_paid_only_when_fully_paid"), "installments", type_="check"
    )
    op.drop_constraint(
        op.f("ck_installments_paid_amount_within_amount"), "installments", type_="check"
    )
    op.drop_column("installments", "paid_amount")
    op.drop_index(
        op.f("ix_installment_payments_installment_id"),
        table_name="installment_payments",
    )
    op.drop_table("installment_payments")

"""create installment change logs table

Revision ID: 762dfa9f2f6a
Revises: aa421f707e95
Create Date: 2026-10-25 19:01:52.777205

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "762dfa9f2f6a"
down_revision: str | Sequence[str] | None = "aa421f707e95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "installment_change_logs",
        sa.Column("installment_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_id", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "change",
            sa.Enum(
                "payment_recorded",
                "payment_corrected",
                "payment_reversed",
                "due_date_edited",
                "amount_edited",
                name="installment_change",
                native_enum=False,
                create_constraint=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("old_value", sa.String(), nullable=True),
        sa.Column("new_value", sa.String(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "change IN ('payment_recorded', 'payment_corrected', 'payment_reversed', 'due_date_edited', 'amount_edited')",
            name=op.f("ck_installment_change_logs_installment_change"),
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["users.id"],
            name=op.f("fk_installment_change_logs_changed_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["installment_id"],
            ["installments.id"],
            name=op.f("fk_installment_change_logs_installment_id_installments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_installment_change_logs")),
    )
    op.create_index(
        op.f("ix_installment_change_logs_installment_id"),
        "installment_change_logs",
        ["installment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_installment_change_logs_installment_id"),
        table_name="installment_change_logs",
    )
    op.drop_table("installment_change_logs")

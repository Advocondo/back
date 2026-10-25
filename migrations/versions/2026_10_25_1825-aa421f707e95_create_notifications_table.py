"""create notifications table

Revision ID: aa421f707e95
Revises: 183ab32038c5
Create Date: 2026-10-25 18:25:11.875807

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aa421f707e95"
down_revision: str | Sequence[str] | None = "183ab32038c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("installment_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["installment_id"],
            ["installments.id"],
            name=op.f("fk_notifications_installment_id_installments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "user_id",
            "installment_id",
            name=op.f("uq_notifications_user_id_installment_id"),
        ),
    )
    op.create_index(
        op.f("ix_notifications_installment_id"),
        "notifications",
        ["installment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_installment_id"), table_name="notifications")
    op.drop_table("notifications")

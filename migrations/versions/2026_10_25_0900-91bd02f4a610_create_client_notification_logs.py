"""create client notification logs

Revision ID: 91bd02f4a610
Revises: 183ab32038c5
Create Date: 2026-10-25 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "91bd02f4a610"
down_revision: str | Sequence[str] | None = "183ab32038c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_notification_logs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("condominium_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=1000), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "event_type IN ('agreement_created', 'agreement_updated', "
            "'agreement_cancelled', 'payment_updated', 'condominium_updated', "
            "'monthly_report_ready')",
            name=op.f("ck_client_notification_logs_client_notification_event"),
        ),
        sa.ForeignKeyConstraint(
            ["condominium_id"],
            ["condominiums.id"],
            name=op.f("fk_client_notification_logs_condominium_id_condominiums"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_client_notification_logs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_notification_logs")),
    )
    op.create_index(
        op.f("ix_client_notification_logs_condominium_id"),
        "client_notification_logs",
        ["condominium_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_notification_logs_user_id"),
        "client_notification_logs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_client_notification_logs_user_id"),
        table_name="client_notification_logs",
    )
    op.drop_index(
        op.f("ix_client_notification_logs_condominium_id"),
        table_name="client_notification_logs",
    )
    op.drop_table("client_notification_logs")

"""add user audit logs

Revision ID: de7be5d29c0e
Revises: 7328a7cea479
Create Date: 2026-10-19 01:51:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "de7be5d29c0e"
down_revision: str | Sequence[str] | None = "7328a7cea479"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_audit_logs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("old_value", sa.String(length=255), nullable=True),
        sa.Column("new_value", sa.String(length=255), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_user_audit_logs_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_audit_logs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_audit_logs")),
    )
    op.create_index(
        op.f("ix_user_audit_logs_user_id"),
        "user_audit_logs",
        ["user_id"],
        unique=False,
    )
    op.create_check_constraint(
        op.f("ck_user_audit_logs_action"),
        "user_audit_logs",
        "action IN ('invited', 'status_changed', 'role_changed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_user_audit_logs_action"), "user_audit_logs", type_="check"
    )
    op.drop_index(op.f("ix_user_audit_logs_user_id"), table_name="user_audit_logs")
    op.drop_table("user_audit_logs")

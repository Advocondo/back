"""create users table

Revision ID: 0f214271f4c1
Revises:
Create Date: 2026-10-10 12:18:55.571858

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0f214271f4c1"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.CheckConstraint(
            "role IN ('admin', 'operator', 'client')", name=op.f("ck_users_role")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'inactive')",
            name=op.f("ck_users_user_status"),
        ),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_users_email_is_lowercase")
        ),
        sa.CheckConstraint(
            "status <> 'active' OR password_hash IS NOT NULL",
            name=op.f("ck_users_active_user_has_password"),
        ),
    )


def downgrade() -> None:
    op.drop_table("users")

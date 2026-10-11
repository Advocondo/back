"""create password reset links table

Revision ID: 0557c13f7116
Revises: 2320693c0417
Create Date: 2026-10-11 12:35:25.999472

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0557c13f7116"
down_revision: str | Sequence[str] | None = "2320693c0417"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_links",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_links_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_links")),
        sa.UniqueConstraint(
            "token_hash", name=op.f("uq_password_reset_links_token_hash")
        ),
    )
    op.create_index(
        op.f("ix_password_reset_links_user_id"),
        "password_reset_links",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_password_reset_links_user_id"), table_name="password_reset_links"
    )
    op.drop_table("password_reset_links")

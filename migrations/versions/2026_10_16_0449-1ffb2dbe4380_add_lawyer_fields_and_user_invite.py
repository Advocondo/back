"""add lawyer fields and user invite

Revision ID: 1ffb2dbe4380
Revises: 0557c13f7116
Create Date: 2026-10-16 04:49:20.158006

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1ffb2dbe4380"
down_revision: str | Sequence[str] | None = "0557c13f7116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_lawyer", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("oab_number", sa.String(length=12), nullable=True))
    op.create_check_constraint(
        op.f("ck_users_lawyer_has_valid_oab_number"),
        "users",
        "(NOT is_lawyer AND oab_number IS NULL) "
        "OR (is_lawyer AND oab_number IS NOT NULL "
        "AND char_length(oab_number) BETWEEN 8 AND 12)",
    )

    op.create_table(
        "user_invites",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
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
            name=op.f("fk_user_invites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.id"],
            name=op.f("fk_user_invites_invited_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_invites")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_invites_token_hash")),
    )
    op.create_index(
        op.f("ix_user_invites_user_id"), "user_invites", ["user_id"], unique=True
    )
    op.create_index(
        op.f("ix_user_invites_invited_by_id"),
        "user_invites",
        ["invited_by_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_invites_invited_by_id"), table_name="user_invites")
    op.drop_index(op.f("ix_user_invites_user_id"), table_name="user_invites")
    op.drop_table("user_invites")
    op.drop_constraint(
        op.f("ck_users_lawyer_has_valid_oab_number"), "users", type_="check"
    )
    op.drop_column("users", "oab_number")
    op.drop_column("users", "is_lawyer")

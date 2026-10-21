"""link users to condominiums

Revision ID: a3c5e8d19b72
Revises: 3c0def97fc59
Create Date: 2026-10-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e8d19b72"
down_revision: str | Sequence[str] | None = "3c0def97fc59"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_condominiums",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("condominium_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_condominiums_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["condominium_id"],
            ["condominiums.id"],
            name=op.f("fk_user_condominiums_condominium_id_condominiums"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "condominium_id", name=op.f("pk_user_condominiums")
        ),
    )
    op.create_index(
        op.f("ix_user_condominiums_condominium_id"),
        "user_condominiums",
        ["condominium_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_condominiums_condominium_id"), table_name="user_condominiums"
    )
    op.drop_table("user_condominiums")

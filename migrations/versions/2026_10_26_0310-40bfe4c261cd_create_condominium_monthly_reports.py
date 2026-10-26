"""create condominium monthly reports

Revision ID: 40bfe4c261cd
Revises: 91bd02f4a610
Create Date: 2026-10-26 03:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "40bfe4c261cd"
down_revision: str | Sequence[str] | None = "91bd02f4a610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "condominium_monthly_reports",
        sa.Column("condominium_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "month BETWEEN 1 AND 12",
            name=op.f("ck_condominium_monthly_reports_month_in_range"),
        ),
        sa.CheckConstraint(
            "(content IS NULL) <> (storage_key IS NULL)",
            name=op.f("ck_condominium_monthly_reports_stored_in_one_place"),
        ),
        sa.ForeignKeyConstraint(
            ["condominium_id"],
            ["condominiums.id"],
            name=op.f("fk_condominium_monthly_reports_condominium_id_condominiums"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_condominium_monthly_reports")),
        sa.UniqueConstraint(
            "condominium_id",
            "year",
            "month",
            name=op.f("uq_condominium_monthly_reports_condominium_id"),
        ),
    )
    op.create_index(
        op.f("ix_condominium_monthly_reports_condominium_id"),
        "condominium_monthly_reports",
        ["condominium_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_condominium_monthly_reports_condominium_id"),
        table_name="condominium_monthly_reports",
    )
    op.drop_table("condominium_monthly_reports")

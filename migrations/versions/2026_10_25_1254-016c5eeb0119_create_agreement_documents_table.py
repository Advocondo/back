"""create agreement documents table

Revision ID: 016c5eeb0119
Revises: 183ab32038c5
Create Date: 2026-10-25 12:54:46.449373

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016c5eeb0119"
down_revision: str | Sequence[str] | None = "183ab32038c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agreement_documents",
        sa.Column("agreement_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "size > 0", name=op.f("ck_agreement_documents_size_is_positive")
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["agreements.id"],
            name=op.f("fk_agreement_documents_agreement_id_agreements"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_agreement_documents_uploaded_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agreement_documents")),
        sa.Index(
            op.f("ix_agreement_documents_agreement_id"),
            "agreement_id",
            unique=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("agreement_documents")

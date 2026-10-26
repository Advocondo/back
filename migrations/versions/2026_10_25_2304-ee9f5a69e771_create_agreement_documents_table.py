"""create agreement documents and document files tables

Revision ID: ee9f5a69e771
Revises: 762dfa9f2f6a
Create Date: 2026-10-25 23:04:57.554831

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ee9f5a69e771"
down_revision: str | Sequence[str] | None = "762dfa9f2f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Os bytes dos arquivos ficam numa tabela própria, com as colunas do
    # StoredFileMixin (banco ou bucket); o link não tem linha nela.
    op.create_table(
        "agreement_document_files",
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "(content IS NULL) <> (storage_key IS NULL)",
            name=op.f("ck_agreement_document_files_stored_in_one_place"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_agreement_document_files_size_is_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agreement_document_files")),
    )
    op.create_table(
        "agreement_documents",
        sa.Column("agreement_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "(file_id IS NULL) <> (url IS NULL)",
            name=op.f("ck_agreement_documents_file_or_link"),
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["agreements.id"],
            name=op.f("fk_agreement_documents_agreement_id_agreements"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["agreement_document_files.id"],
            name=op.f("fk_agreement_documents_file_id_agreement_document_files"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_agreement_documents_uploaded_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agreement_documents")),
        sa.UniqueConstraint("file_id", name=op.f("uq_agreement_documents_file_id")),
    )
    op.create_index(
        op.f("ix_agreement_documents_agreement_id"),
        "agreement_documents",
        ["agreement_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agreement_documents_agreement_id"), table_name="agreement_documents"
    )
    op.drop_table("agreement_documents")
    op.drop_table("agreement_document_files")

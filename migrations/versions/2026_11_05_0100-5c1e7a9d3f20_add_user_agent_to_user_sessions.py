"""add user agent to user sessions

Revision ID: 5c1e7a9d3f20
Revises: 40bfe4c261cd
Create Date: 2026-11-05 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5c1e7a9d3f20"
down_revision: str | Sequence[str] | None = "40bfe4c261cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_sessions", sa.Column("user_agent", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_sessions", "user_agent")

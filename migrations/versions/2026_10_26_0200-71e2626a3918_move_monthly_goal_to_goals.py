"""move users.monthly_goal to the goals table

A meta mensal estava em dois lugares: a tabela goals da US36, uma meta por mês, e
o campo users.monthly_goal, criado para o painel da US32. O painel passa a ler
goals, e o campo sai. Antes, cada meta maior que zero gravada no campo vira a meta
do mês atual (no horário de Brasília) do mesmo usuário, se ele ainda não tiver uma.

Revision ID: 71e2626a3918
Revises: ee9f5a69e771
Create Date: 2026-10-26 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "71e2626a3918"
down_revision: str | Sequence[str] | None = "ee9f5a69e771"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO goals (user_id, year, month, target_amount)
        SELECT
            users.id,
            EXTRACT(YEAR FROM now() AT TIME ZONE 'America/Sao_Paulo'),
            EXTRACT(MONTH FROM now() AT TIME ZONE 'America/Sao_Paulo'),
            users.monthly_goal
        FROM users
        WHERE users.monthly_goal > 0 AND users.role = 'operator'
        ON CONFLICT (user_id, year, month) DO NOTHING
        """
    )
    op.drop_column("users", "monthly_goal")


def downgrade() -> None:
    # As metas continuam em goals; o campo volta zerado, como foi criado.
    op.add_column(
        "users",
        sa.Column(
            "monthly_goal",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
    )

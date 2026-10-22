import uuid
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from advocondo.metas.attainment import GoalProgress
from advocondo.metas.models import MAX_TARGET_DIGITS, TARGET_DECIMAL_PLACES


class GoalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_amount: Decimal = Field(
        gt=0, max_digits=MAX_TARGET_DIGITS, decimal_places=TARGET_DECIMAL_PLACES
    )


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    year: int
    month: int
    target_amount: Decimal


class GoalProgressResponse(GoalResponse):
    """A meta do mês com o que já foi alcançado (US36)."""

    achieved_amount: Decimal
    attainment_percentage: Decimal

    @classmethod
    def from_progress(cls, progress: GoalProgress) -> Self:
        goal = progress.goal
        return cls(
            id=goal.id,
            user_id=goal.user_id,
            year=goal.year,
            month=goal.month,
            target_amount=goal.target_amount,
            achieved_amount=progress.achieved_amount,
            attainment_percentage=progress.attainment_percentage,
        )

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from advocondo.metas.models import MAX_TARGET_DIGITS, TARGET_DECIMAL_PLACES


class GoalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_amount: Decimal = Field(
        gt=0, max_digits=MAX_TARGET_DIGITS, decimal_places=TARGET_DECIMAL_PLACES
    )
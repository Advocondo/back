import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from advocondo.acordos.schemas import MoneyResponse


class InstallmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agreement_id: uuid.UUID
    number: int
    due_date: date
    amount: MoneyResponse
    payment_date: date | None

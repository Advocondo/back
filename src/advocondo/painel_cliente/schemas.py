import enum
import uuid
from datetime import date

from pydantic import BaseModel

from advocondo.acordos.schemas import MoneyResponse
from advocondo.parcelas.status import InstallmentStatus


class AgreementStanding(enum.StrEnum):
    """Situação simplificada do acordo, vista pelo Cliente (US37)."""

    ON_TIME = "em_dia"
    OVERDUE = "atrasado"


class AgreementSummary(BaseModel):
    """Lista fechada de campos: nenhum valor, honorário ou comissão do escritório
    entra aqui (US37-CA02), então um campo novo no acordo não vaza por padrão."""

    id: uuid.UUID
    condominium_name: str
    debtor_name: str
    debtor_unit: str
    status: AgreementStanding
    overdue_installments: int
    next_due_date: date | None


class ClientInstallment(BaseModel):
    """Parcela sem pagamento vista pelo Cliente (#89). Lista fechada de campos, como
    no resumo: nem honorários nem a divisão do valor entram aqui (US38-CA01)."""

    number: int
    due_date: date
    amount: MoneyResponse
    # Quanto falta pagar; menor que `amount` depois de um pagamento parcial (US28).
    remaining_amount: MoneyResponse
    status: InstallmentStatus

"""Regra pura da situação da parcela, calculada a partir das datas (US27)."""
import enum
from datetime import date


class InstallmentStatus(enum.StrEnum):
    """Situação da parcela exibida ao usuário. É calculada, nunca gravada."""

    OPEN = "open"
    PAID = "paid"
    OVERDUE = "overdue"


def calculate_installment_status(
    due_date: date, payment_date: date | None, today: date
) -> InstallmentStatus:
    """Devolve a situação da parcela na data `today`.

    Parcela com data de pagamento está paga, mesmo que o pagamento tenha sido
    feito depois do vencimento. Sem data de pagamento, ela passa a ser atrasada
    no dia seguinte ao vencimento.
    """
    if payment_date is not None:
        return InstallmentStatus.PAID

    if today > due_date:
        return InstallmentStatus.OVERDUE

    return InstallmentStatus.OPEN

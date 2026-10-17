import enum
from datetime import date


class ParcelaStatus(enum.StrEnum):
    """Situação da parcela exibida ao usuário. É calculada, nunca gravada."""

    EM_ABERTO = "em_aberto"
    PAGO = "pago"
    ATRASADO = "atrasado"


def calculate_parcela_status(
    due_date: date, payment_date: date | None, today: date
) -> ParcelaStatus:
    """Devolve a situação da parcela na data `today`.

    Parcela com data de pagamento está paga, mesmo que o pagamento tenha sido
    feito depois do vencimento. Sem data de pagamento, ela passa a ser atrasada
    no dia seguinte ao vencimento.
    """
    if payment_date is not None:
        return ParcelaStatus.PAGO

    if today > due_date:
        return ParcelaStatus.ATRASADO

    return ParcelaStatus.EM_ABERTO

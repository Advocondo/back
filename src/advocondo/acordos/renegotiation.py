"""Regras puras da alteração de um acordo (US19)."""

from dataclasses import dataclass
from decimal import Decimal

from advocondo.acordos.errors import (
    FeeAboveTotalError,
    FeeIncompatibleWithPaidError,
    NoOpenInstallmentError,
    TotalBelowPaidAmountError,
)
from advocondo.acordos.fees import fee_from_percentage
from advocondo.parcelas.plan import split_amount, split_fee


@dataclass(frozen=True)
class Fee:
    """Honorários depois da alteração: o valor em reais e o percentual, se foi digitado."""

    amount: Decimal
    percentage: Decimal | None


@dataclass(frozen=True)
class OpenInstallmentValues:
    amount: Decimal
    fee_amount: Decimal


def fee_after_edit(
    new_total: Decimal,
    typed_percentage: Decimal | None,
    typed_amount: Decimal | None,
    stored_percentage: Decimal | None,
    stored_amount: Decimal,
) -> Fee:
    """Honorários do acordo alterado.

    Vale o que foi digitado agora. Sem nada digitado, o percentual guardado continua
    valendo sobre o novo total; sem percentual, o valor em reais não muda.
    """
    if typed_amount is not None:
        fee = Fee(typed_amount, None)
    elif typed_percentage is not None:
        fee = Fee(fee_from_percentage(new_total, typed_percentage), typed_percentage)
    elif stored_percentage is not None:
        fee = Fee(fee_from_percentage(new_total, stored_percentage), stored_percentage)
    else:
        fee = Fee(stored_amount, None)

    if fee.amount > new_total:
        raise FeeAboveTotalError()
    return fee


def recalculate_open_installments(
    new_total: Decimal,
    new_fee: Decimal,
    paid_amount: Decimal,
    paid_fee: Decimal,
    open_count: int,
) -> list[OpenInstallmentValues]:
    """Valores novos das parcelas em aberto depois de mudar o total ou os honorários.

    As parcelas pagas não mudam: o que falta receber é dividido em partes iguais
    entre as parcelas em aberto.
    """
    if open_count == 0:
        raise NoOpenInstallmentError()
    remaining = new_total - paid_amount
    if remaining <= 0:
        raise TotalBelowPaidAmountError()
    remaining_fee = new_fee - paid_fee
    if remaining_fee < 0 or remaining_fee > remaining:
        raise FeeIncompatibleWithPaidError()

    amounts = split_amount(remaining, open_count)
    fees = split_fee(amounts, remaining_fee)
    return [
        OpenInstallmentValues(amount, fee)
        for amount, fee in zip(amounts, fees, strict=True)
    ]

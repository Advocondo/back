from decimal import Decimal

from advocondo.common.errors import BusinessRuleError, ConflictError, NotFoundError
from advocondo.common.money import format_brl


class AgreementNotFoundError(NotFoundError):
    message = "Acordo não encontrado."


class DebtorFromAnotherCondominiumError(BusinessRuleError):
    message = "O devedor informado não pertence a este condomínio."


class FeeAboveTotalError(BusinessRuleError):
    message = "Os honorários não podem ser maiores que o valor total do acordo."


class PaidInstallmentsNeedConfirmationError(ConflictError):
    message = "Este acordo já tem parcelas pagas. Confirme a alteração para continuar."


class TotalBelowPaidAmountError(BusinessRuleError):
    message = "O novo valor total precisa ser maior que o valor das parcelas já pagas."


class FeeIncompatibleWithPaidError(BusinessRuleError):
    message = "Os honorários não são compatíveis com as parcelas já pagas."


class NoOpenInstallmentError(BusinessRuleError):
    message = (
        "Todas as parcelas já foram pagas: não há parcela em aberto para recalcular."
    )


class LawyerNotFoundError(NotFoundError):
    message = "Advogado não encontrado."


class LawyerNotEligibleError(BusinessRuleError):
    message = "O responsável precisa ser um advogado ativo, com OAB cadastrada."


class AgreementAlreadyCancelledError(BusinessRuleError):
    message = "O acordo já está cancelado."


class AgreementCancelledError(BusinessRuleError):
    message = "Acordo cancelado não aceita esta operação."


class AgreementNotCancelledError(BusinessRuleError):
    message = "O acordo não está cancelado."


class OpenInstallmentsNotConfirmedError(ConflictError):
    """O acordo ainda tem parcelas sem pagamento e o usuário não confirmou (US20)."""

    def __init__(self, count: int, total: Decimal) -> None:
        noun = "parcela sem pagamento" if count == 1 else "parcelas sem pagamento"
        super().__init__(
            f"Há {count} {noun}, somando {format_brl(total)}. "
            "Confirme para cancelar o acordo."
        )

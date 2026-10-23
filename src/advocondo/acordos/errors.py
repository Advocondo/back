from advocondo.common.errors import BusinessRuleError, ConflictError, NotFoundError


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

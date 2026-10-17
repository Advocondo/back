from advocondo.common.errors import BusinessRuleError, NotFoundError


class AgreementNotFoundError(NotFoundError):
    message = "Acordo não encontrado."


class DebtorFromAnotherCondominiumError(BusinessRuleError):
    message = "O devedor informado não pertence a este condomínio."

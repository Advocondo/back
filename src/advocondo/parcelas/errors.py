from advocondo.common.errors import BusinessRuleError, NotFoundError


class InstallmentNotFoundError(NotFoundError):
    message = "Parcela não encontrada."


class InstallmentBelowOneCentError(BusinessRuleError):
    message = (
        "Cada parcela precisa ter pelo menos R$ 0,01. Diminua o número de parcelas."
    )

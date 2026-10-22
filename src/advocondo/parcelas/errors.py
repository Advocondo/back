from advocondo.common.errors import BusinessRuleError, NotFoundError


class InstallmentNotFoundError(NotFoundError):
    message = "Parcela não encontrada."


class InstallmentBelowOneCentError(BusinessRuleError):
    message = (
        "Cada parcela precisa ter pelo menos R$ 0,01. Diminua o número de parcelas."
    )


class PaidInstallmentCannotBeEditedError(BusinessRuleError):
    message = "Parcela já paga não pode ser editada."


class NoOpenInstallmentAfterError(BusinessRuleError):
    message = (
        "Não há parcela seguinte em aberto para absorver a diferença de valor. "
        "Para mudar o total, edite o acordo."
    )


class FollowingInstallmentWouldBeEmptyError(BusinessRuleError):
    message = "A diferença deixaria alguma parcela seguinte sem valor."


class InstallmentAlreadyPaidError(BusinessRuleError):
    message = "Parcela já paga. Para mudar a data do pagamento, corrija a baixa."


class InstallmentNotPaidError(BusinessRuleError):
    message = "A parcela ainda não foi paga."


class PaymentDateInTheFutureError(BusinessRuleError):
    message = "A data do pagamento não pode ser futura."

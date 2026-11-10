from advocondo.common.errors import BusinessRuleError


class InvalidAuditPeriodError(BusinessRuleError):
    message = "A data inicial não pode ser depois da data final."

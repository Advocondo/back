from advocondo.common.errors import BusinessRuleError, ConflictError, NotFoundError


class CondominiumNotFoundError(NotFoundError):
    message = "Condomínio não encontrado."


class CnpjAlreadyRegisteredError(ConflictError):
    message = "Já existe um condomínio com este CNPJ."


class InvalidContractDatesError(BusinessRuleError):
    message = "A data de renovação não pode ser anterior ao início do contrato."

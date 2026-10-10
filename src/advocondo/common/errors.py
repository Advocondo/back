"""Errors that services raise to refuse an operation; main.py maps each to an HTTP status.

The message is shown to the end user, so it is in Portuguese and has no internal details.
"""


class AppError(Exception):
    message = "Não foi possível concluir a operação."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class AuthenticationError(AppError):
    message = "Faça login para continuar."


class PermissionDeniedError(AppError):
    message = "Você não tem permissão para esta operação."


class NotFoundError(AppError):
    message = "Registro não encontrado."


class ConflictError(AppError):
    message = "A operação conflita com um registro existente."


class BusinessRuleError(AppError):
    message = "A operação não é permitida."

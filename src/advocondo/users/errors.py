from advocondo.common.errors import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)


class FirstUserAlreadyCreatedError(BusinessRuleError):
    message = "O primeiro usuário já foi criado. Os demais entram por convite."


class PasswordTooShortError(BusinessRuleError):
    def __init__(self, min_length: int) -> None:
        super().__init__(f"A senha precisa ter pelo menos {min_length} caracteres.")


class SetupDisabledError(NotFoundError):
    pass


class InvalidSetupTokenError(PermissionDeniedError):
    message = "Token de configuração inválido."


class CurrentPasswordRequiredError(BusinessRuleError):
    message = "Informe a senha atual para alterar o e-mail ou a senha."


class WrongCurrentPasswordError(BusinessRuleError):
    message = "A senha atual está incorreta."


class EmailAlreadyInUseError(ConflictError):
    message = "Este e-mail já está em uso por outro usuário."


class OabNumberRequiredError(BusinessRuleError):
    message = "Informe o número da OAB para marcar o usuário como advogado."


class OabNumberNotAllowedError(BusinessRuleError):
    message = "O número da OAB só pode ser informado para advogados."


class InvalidInviteTokenError(BusinessRuleError):
    message = "O convite é inválido ou já expirou."


class AdminRoleNotAllowedError(BusinessRuleError):
    message = "Não é possível convidar outro Administrador."

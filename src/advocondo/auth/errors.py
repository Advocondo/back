from advocondo.common.errors import AuthenticationError, BusinessRuleError


class InvalidCredentialsError(AuthenticationError):
    # Same message for unknown e-mail, wrong password and inactive user (US02-CA02).
    message = "E-mail ou senha inválidos."


class InvalidSessionError(AuthenticationError):
    message = "Sua sessão expirou. Faça login novamente."


class InvalidPasswordResetLinkError(BusinessRuleError):
    # Same message for unknown, used and expired links (US03-CA02).
    message = "Este link de redefinição é inválido ou expirou. Solicite um novo."

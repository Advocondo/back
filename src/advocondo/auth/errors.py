from advocondo.common.errors import AuthenticationError


class InvalidCredentialsError(AuthenticationError):
    # Same message for unknown e-mail, wrong password and inactive user (US02-CA02).
    message = "E-mail ou senha inválidos."


class InvalidSessionError(AuthenticationError):
    message = "Sua sessão expirou. Faça login novamente."

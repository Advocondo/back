from advocondo.common.errors import BusinessRuleError


class FirstUserAlreadyCreatedError(BusinessRuleError):
    message = "O primeiro usuário já foi criado. Os demais entram por convite."


class PasswordTooShortError(BusinessRuleError):
    def __init__(self, min_length: int) -> None:
        super().__init__(f"A senha precisa ter pelo menos {min_length} caracteres.")

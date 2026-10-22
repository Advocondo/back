from advocondo.common.errors import BusinessRuleError, ConflictError, NotFoundError
from advocondo.devedores.models import Debtor


class DebtorNotFoundError(NotFoundError):
    message = "Devedor não encontrado."


class ContactRequiredError(BusinessRuleError):
    message = "Informe o telefone ou o e-mail do devedor."


class SimilarDebtorsFoundError(ConflictError):
    """Not a refusal: the user may confirm and register the debtor anyway."""

    message = (
        "Já existe devedor com dados parecidos neste condomínio. "
        "Confira a lista e confirme se quiser cadastrar mesmo assim."
    )

    def __init__(self, similar_debtors: list[Debtor]) -> None:
        super().__init__()
        self.similar_debtors = similar_debtors


class InvalidSpreadsheetError(BusinessRuleError):
    message = "Não foi possível ler a planilha. Envie um arquivo .xlsx."

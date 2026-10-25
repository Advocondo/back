from advocondo.common.errors import NotFoundError


class AgreementPdfNotFoundError(NotFoundError):
    message = "PDF não encontrado."

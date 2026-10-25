from advocondo.common.errors import BusinessRuleError, NotFoundError


class DocumentNotFoundError(NotFoundError):
    message = "Documento não encontrado."


class EmptyDocumentError(BusinessRuleError):
    message = "O arquivo está vazio."


class DocumentTooLargeError(BusinessRuleError):
    message = "O arquivo passa de 10 MB."


class UnsupportedDocumentTypeError(BusinessRuleError):
    message = "Tipo de arquivo não aceito. Envie PDF, PNG ou JPEG."


class AgreementPdfNotFoundError(NotFoundError):
    message = "PDF não encontrado."

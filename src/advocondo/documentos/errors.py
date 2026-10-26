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


class InvalidUrlError(BusinessRuleError):
    message = "Endereço inválido. Informe um link http ou https."


class FileOrLinkRequiredError(BusinessRuleError):
    message = "Envie um arquivo ou um link, mas não os dois."


class DocumentIsALinkError(BusinessRuleError):
    message = "Este documento é um link: abra o endereço informado."

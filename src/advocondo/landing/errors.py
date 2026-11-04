from advocondo.common.errors import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)


class LandingImageNotFoundError(NotFoundError):
    message = "Imagem não encontrada."


class UnknownLandingImageError(BusinessRuleError):
    message = "A página usa uma imagem que não foi enviada. Envie a imagem de novo."


class LandingImageInUseError(ConflictError):
    message = "A imagem está em uso na página institucional."


class UnsupportedLandingImageError(BusinessRuleError):
    message = "Envie uma imagem PNG, JPEG ou WebP."


class LandingImageTooLargeError(BusinessRuleError):
    def __init__(self, max_kilobytes: int) -> None:
        super().__init__(f"A imagem passa de {max_kilobytes} KB.")


class InvalidCaptchaError(BusinessRuleError):
    message = (
        "Não foi possível confirmar o envio. Refaça a verificação e tente de novo."
    )


class ContactFormUnavailableError(ServiceUnavailableError):
    # The message was not saved anywhere, so the visitor needs to know it did not go out.
    message = (
        "Não foi possível enviar sua mensagem. "
        "Tente mais tarde ou fale conosco por telefone."
    )

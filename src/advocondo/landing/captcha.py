import json
import logging
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from advocondo.common.email import LOCAL_ENVIRONMENT
from advocondo.config import Settings, get_settings
from advocondo.landing.errors import ContactFormUnavailableError

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TIMEOUT_SECONDS = 5


class CaptchaVerifier(Protocol):
    def is_valid(self, token: str) -> bool: ...


class TurnstileVerifier:
    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key

    def is_valid(self, token: str) -> bool:
        body = urlencode({"secret": self._secret_key, "response": token}).encode()
        request = Request(TURNSTILE_VERIFY_URL, data=body)
        try:
            with urlopen(request, timeout=TURNSTILE_TIMEOUT_SECONDS) as response:
                return json.load(response).get("success") is True
        except (OSError, ValueError) as error:
            # Not the visitor's fault, so it must not read as a failed verification.
            logger.exception("Falha ao consultar o Turnstile")
            raise ContactFormUnavailableError() from error


class LocalCaptchaVerifier:
    """Local development only: accepts every token, as there is no site key here."""

    def is_valid(self, token: str) -> bool:
        return True


class UnconfiguredCaptchaVerifier:
    """Without the key the form stays closed, instead of open to spam."""

    def is_valid(self, token: str) -> bool:
        logger.error("TURNSTILE_SECRET_KEY não está definida")
        raise ContactFormUnavailableError()


def build_captcha_verifier(settings: Settings) -> CaptchaVerifier:
    if settings.turnstile_secret_key:
        return TurnstileVerifier(settings.turnstile_secret_key)
    if settings.environment == LOCAL_ENVIRONMENT:
        return LocalCaptchaVerifier()
    return UnconfiguredCaptchaVerifier()


def get_captcha_verifier() -> CaptchaVerifier:
    return build_captcha_verifier(get_settings())

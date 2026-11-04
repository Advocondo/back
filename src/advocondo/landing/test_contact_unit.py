import io
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import Request

import pytest
from pydantic import ValidationError

from advocondo.landing import captcha as captcha_module
from advocondo.landing.captcha import (
    TURNSTILE_VERIFY_URL,
    LocalCaptchaVerifier,
    TurnstileVerifier,
    UnconfiguredCaptchaVerifier,
    build_captcha_verifier,
    get_captcha_verifier,
)
from advocondo.landing.contact import build_contact_email
from advocondo.landing.errors import ContactFormUnavailableError
from advocondo.landing.schemas import ContactMessageRequest
from tests.support.settings import make_settings

VALID_MESSAGE: dict[str, Any] = {
    "name": "Ana Souza",
    "phone": "(61) 91234-5678",
    "email": "ana@example.com",
}


class TestContactMessageRequest:
    def test_keeps_only_the_digits_of_the_phone(self) -> None:
        assert ContactMessageRequest(**VALID_MESSAGE).phone == "61912345678"

    @pytest.mark.parametrize(
        "changes",
        [
            pytest.param({"name": "   "}, id="blank-name"),
            pytest.param({"phone": "123"}, id="short-phone"),
            pytest.param({"email": "ana@"}, id="invalid-email"),
            pytest.param({"message": "x" * 1001}, id="long-message"),
            pytest.param({"unknown": "x"}, id="unknown-field"),
        ],
    )
    def test_refuses_invalid_fields(self, changes: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            ContactMessageRequest(**(VALID_MESSAGE | changes))


class TestContactEmail:
    def test_goes_to_the_office_and_replies_go_to_the_visitor(self) -> None:
        request = ContactMessageRequest(**VALID_MESSAGE, message="Preciso de ajuda.")

        email = build_contact_email(request, "contato@example.com")

        assert email.to == "contato@example.com"
        assert email.reply_to == "ana@example.com"
        for text in (
            "Ana Souza",
            "61912345678",
            "ana@example.com",
            "Preciso de ajuda.",
        ):
            assert text in email.body

    def test_says_so_when_there_is_no_message(self) -> None:
        email = build_contact_email(
            ContactMessageRequest(**VALID_MESSAGE), "contato@example.com"
        )

        assert "(sem mensagem)" in email.body

    def test_a_line_break_in_the_name_cannot_add_headers(self) -> None:
        request = ContactMessageRequest(**(VALID_MESSAGE | {"name": "Ana\nBcc: x@y.z"}))

        email = build_contact_email(request, "contato@example.com")

        assert "\n" not in email.subject
        assert email.to == "contato@example.com"


class TestTurnstileVerifier:
    @pytest.fixture
    def requests(self) -> list[Request]:
        return []

    def answer_with(
        self, monkeypatch: pytest.MonkeyPatch, requests: list[Request], body: bytes
    ) -> None:
        def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
            requests.append(request)
            return io.BytesIO(body)

        monkeypatch.setattr(captcha_module, "urlopen", fake_urlopen)

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            pytest.param(b'{"success": true}', True, id="accepted"),
            pytest.param(b'{"success": false}', False, id="refused"),
            pytest.param(b"{}", False, id="no-answer"),
        ],
    )
    def test_trusts_only_an_explicit_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
        requests: list[Request],
        body: bytes,
        expected: bool,
    ) -> None:
        self.answer_with(monkeypatch, requests, body)

        assert TurnstileVerifier("chave").is_valid("token") is expected

    def test_sends_the_key_and_the_token_to_cloudflare(
        self, monkeypatch: pytest.MonkeyPatch, requests: list[Request]
    ) -> None:
        self.answer_with(monkeypatch, requests, b'{"success": true}')

        TurnstileVerifier("chave").is_valid("token")

        assert requests[0].full_url == TURNSTILE_VERIFY_URL
        assert isinstance(requests[0].data, bytes)
        assert parse_qs(requests[0].data.decode()) == {
            "secret": ["chave"],
            "response": ["token"],
        }

    def test_an_unreadable_answer_makes_the_form_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, requests: list[Request]
    ) -> None:
        self.answer_with(monkeypatch, requests, b"<html>")

        with pytest.raises(ContactFormUnavailableError):
            TurnstileVerifier("chave").is_valid("token")

    def test_cloudflare_being_down_makes_the_form_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_urlopen(request: Request, timeout: int) -> io.BytesIO:
            raise URLError("fora do ar")

        monkeypatch.setattr(captcha_module, "urlopen", broken_urlopen)

        with pytest.raises(ContactFormUnavailableError):
            TurnstileVerifier("chave").is_valid("token")


class TestBuildCaptchaVerifier:
    def test_uses_turnstile_when_the_key_is_set(self) -> None:
        settings = make_settings(turnstile_secret_key="chave", environment="producao")

        assert isinstance(build_captcha_verifier(settings), TurnstileVerifier)

    def test_accepts_every_token_in_local_development(self) -> None:
        verifier = build_captcha_verifier(
            make_settings(turnstile_secret_key="", environment="local")
        )

        assert isinstance(verifier, LocalCaptchaVerifier)
        assert verifier.is_valid("") is True

    def test_keeps_the_form_closed_without_the_key_elsewhere(self) -> None:
        verifier = build_captcha_verifier(
            make_settings(turnstile_secret_key="", environment="producao")
        )

        assert isinstance(verifier, UnconfiguredCaptchaVerifier)
        with pytest.raises(ContactFormUnavailableError):
            verifier.is_valid("token")

    def test_the_dependency_reads_the_current_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = make_settings(turnstile_secret_key="chave", environment="producao")
        monkeypatch.setattr(captcha_module, "get_settings", lambda: settings)

        assert isinstance(get_captcha_verifier(), TurnstileVerifier)

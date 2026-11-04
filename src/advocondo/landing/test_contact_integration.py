from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from advocondo.common.email import EmailMessage, get_email_sender
from advocondo.landing.captcha import get_captcha_verifier
from advocondo.main import app
from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.users import CreateUser
from tests.support.email import Outbox

pytestmark = pytest.mark.usefixtures("landing_page")

CONTACT_FORM: dict[str, Any] = {
    "name": "Ana Souza",
    "phone": "(61) 91234-5678",
    "email": "ana@example.com",
    "message": "Gostaria de falar sobre o meu condomínio.",
    "website": "",
    "captcha_token": "token-valido",
}
UNAVAILABLE = (
    "Não foi possível enviar sua mensagem. "
    "Tente mais tarde ou fale conosco por telefone."
)


class FakeCaptcha:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def is_valid(self, token: str) -> bool:
        self.tokens.append(token)
        return token == "token-valido"


class BrokenEmailSender:
    def send(self, message: EmailMessage) -> None:
        raise ConnectionError("SMTP fora do ar")


@pytest.fixture
def captcha() -> Iterator[FakeCaptcha]:
    fake = FakeCaptcha()
    app.dependency_overrides[get_captcha_verifier] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_captcha_verifier, None)


class TestSendContactMessage:
    def test_is_public_and_sends_the_message_to_the_contact_email(
        self, db_client: TestClient, captcha: FakeCaptcha, outbox: Outbox
    ) -> None:
        response = db_client.post("/landing/contact", json=CONTACT_FORM)

        assert response.status_code == 204
        assert len(outbox.messages) == 1
        message = outbox.messages[0]
        assert message.to == "contato@example.com"
        assert message.reply_to == "ana@example.com"
        assert "Gostaria de falar sobre o meu condomínio." in message.body

    def test_the_message_is_optional(
        self, db_client: TestClient, captcha: FakeCaptcha, outbox: Outbox
    ) -> None:
        form = {key: value for key, value in CONTACT_FORM.items() if key != "message"}

        response = db_client.post("/landing/contact", json=form)

        assert response.status_code == 204
        assert len(outbox.messages) == 1

    def test_a_filled_honeypot_gets_the_normal_answer_and_sends_nothing(
        self, db_client: TestClient, captcha: FakeCaptcha, outbox: Outbox
    ) -> None:
        form = CONTACT_FORM | {"website": "https://spam.example.com"}

        response = db_client.post("/landing/contact", json=form)

        assert response.status_code == 204
        assert outbox.messages == []
        assert captcha.tokens == []

    def test_a_refused_captcha_sends_nothing(
        self, db_client: TestClient, captcha: FakeCaptcha, outbox: Outbox
    ) -> None:
        form = CONTACT_FORM | {"captcha_token": "token-falso"}

        response = db_client.post("/landing/contact", json=form)

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Não foi possível confirmar o envio. Refaça a verificação e tente de novo."
        )
        assert outbox.messages == []

    def test_a_missing_captcha_token_is_refused(
        self, db_client: TestClient, captcha: FakeCaptcha, outbox: Outbox
    ) -> None:
        form = {k: v for k, v in CONTACT_FORM.items() if k != "captcha_token"}

        response = db_client.post("/landing/contact", json=form)

        assert response.status_code == 422
        assert outbox.messages == []

    def test_an_invalid_field_is_refused(
        self, db_client: TestClient, captcha: FakeCaptcha, outbox: Outbox
    ) -> None:
        response = db_client.post(
            "/landing/contact", json=CONTACT_FORM | {"email": "ana@"}
        )

        assert response.status_code == 422
        assert outbox.messages == []

    def test_a_delivery_failure_tells_the_visitor_it_did_not_go_out(
        self, db_client: TestClient, captcha: FakeCaptcha
    ) -> None:
        app.dependency_overrides[get_email_sender] = BrokenEmailSender
        try:
            response = db_client.post("/landing/contact", json=CONTACT_FORM)
        finally:
            app.dependency_overrides.pop(get_email_sender, None)

        assert response.status_code == 503
        assert response.json()["detail"] == UNAVAILABLE

    def test_a_page_without_a_contact_email_cannot_receive_messages(
        self,
        db_client: TestClient,
        captcha: FakeCaptcha,
        outbox: Outbox,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user(email="adm@example.com", role=Role.ADMIN))
        db_client.patch("/landing", json={"contact": {}}, headers=headers)

        response = db_client.post("/landing/contact", json=CONTACT_FORM)

        assert response.status_code == 503
        assert response.json()["detail"] == UNAVAILABLE
        assert outbox.messages == []

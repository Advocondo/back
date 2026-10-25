from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.common.email import EmailMessage, get_email_sender
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.main import app
from advocondo.notificacoes.models import (
    ClientNotificationEvent,
    ClientNotificationLog,
)
from advocondo.users.models import Role, User, UserStatus
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.painel_cliente import LinkClient
from tests.fixtures.users import CreateUser


class RecordingEmailSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []
        self.fail = False

    def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise OSError("SMTP unavailable")
        self.messages.append(message)


@pytest.fixture
def recording_sender() -> Iterator[RecordingEmailSender]:
    sender = RecordingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        yield sender
    finally:
        app.dependency_overrides.pop(get_email_sender, None)


def test_agreement_creation_emails_and_logs_only_active_linked_clients(
    db_client: TestClient,
    db_session: Session,
    recording_sender: RecordingEmailSender,
    create_user: CreateUser,
    authenticate_as: AuthenticateAs,
    create_condominium: CreateCondominium,
    create_debtor: CreateDebtor,
    link_client: LinkClient,
) -> None:
    condominium = create_condominium(name="Residencial Mirante")
    debtor = create_debtor(condominium)
    linked_client = create_user(
        email="cliente@example.com", role=Role.CLIENT, name="Joana Cliente"
    )
    inactive_client = create_user(
        email="inativo@example.com",
        role=Role.CLIENT,
        status=UserStatus.INACTIVE,
    )
    unrelated_client = create_user(email="alheio@example.com", role=Role.CLIENT)
    link_client(linked_client, condominium)
    link_client(inactive_client, condominium)
    operator = create_user(role=Role.OPERATOR, email="operador@example.com")
    link_client(operator, condominium)

    response = db_client.post(
        "/agreements",
        json={
            "condominium_id": str(condominium.id),
            "debtor_id": str(debtor.id),
            "total_amount": "1000.00",
            "installment_count": 2,
            "first_due_date": "2026-11-10",
            "fee_percentage": "10",
        },
        headers=authenticate_as(operator),
    )

    assert response.status_code == 201
    assert [message.to for message in recording_sender.messages] == [
        linked_client.email
    ]
    email = recording_sender.messages[0]
    assert "novo acordo foi registrado" in email.body
    assert "honorários" not in email.body.lower()
    assert "1000.00" not in email.body
    logs = db_session.scalars(select(ClientNotificationLog)).all()
    assert len(logs) == 1
    assert logs[0].user_id == linked_client.id
    assert logs[0].condominium_id == condominium.id
    assert logs[0].event_type == ClientNotificationEvent.AGREEMENT_CREATED
    assert logs[0].sent_at is not None
    assert logs[0].link == "http://localhost:3000"
    assert unrelated_client.id != logs[0].user_id


def test_email_failure_does_not_undo_agreement_creation_or_log_as_sent(
    db_client: TestClient,
    db_session: Session,
    recording_sender: RecordingEmailSender,
    create_user: CreateUser,
    authenticate_as: AuthenticateAs,
    create_condominium: CreateCondominium,
    create_debtor: CreateDebtor,
    link_client: LinkClient,
) -> None:
    condominium: Condominium = create_condominium()
    debtor: Debtor = create_debtor(condominium)
    client_user: User = create_user(role=Role.CLIENT, email="cliente@example.com")
    link_client(client_user, condominium)
    operator = create_user(role=Role.OPERATOR, email="operador@example.com")
    recording_sender.fail = True

    response = db_client.post(
        "/agreements",
        json={
            "condominium_id": str(condominium.id),
            "debtor_id": str(debtor.id),
            "total_amount": "1000.00",
            "installment_count": 1,
            "first_due_date": "2026-11-10",
            "fee_percentage": "10",
        },
        headers=authenticate_as(operator),
    )

    assert response.status_code == 201
    assert db_session.scalars(select(ClientNotificationLog)).all() == []


def test_agreement_cancellation_notifies_linked_client(
    db_client: TestClient,
    db_session: Session,
    recording_sender: RecordingEmailSender,
    create_user: CreateUser,
    authenticate_as: AuthenticateAs,
    create_condominium: CreateCondominium,
    create_debtor: CreateDebtor,
    link_client: LinkClient,
) -> None:
    condominium = create_condominium()
    debtor = create_debtor(condominium)
    client_user = create_user(role=Role.CLIENT, email="cliente@example.com")
    link_client(client_user, condominium)
    operator = create_user(role=Role.OPERATOR, email="operador@example.com")
    headers = authenticate_as(operator)
    created = db_client.post(
        "/agreements",
        json={
            "condominium_id": str(condominium.id),
            "debtor_id": str(debtor.id),
            "total_amount": "1000.00",
            "installment_count": 1,
            "first_due_date": "2026-11-10",
            "fee_percentage": "10",
        },
        headers=headers,
    )

    cancelled = db_client.post(
        f"/agreements/{created.json()['id']}/cancel",
        json={"confirm_open_installments": True},
        headers=headers,
    )

    assert created.status_code == 201
    assert cancelled.status_code == 200
    assert len(recording_sender.messages) == 2
    logs = db_session.scalars(select(ClientNotificationLog)).all()
    assert {log.event_type for log in logs} == {
        ClientNotificationEvent.AGREEMENT_CREATED,
        ClientNotificationEvent.AGREEMENT_CANCELLED,
    }
    assert all(log.user_id == client_user.id for log in logs)


def test_visible_condominium_update_notifies_linked_client(
    db_client: TestClient,
    db_session: Session,
    recording_sender: RecordingEmailSender,
    create_user: CreateUser,
    authenticate_as: AuthenticateAs,
    create_condominium: CreateCondominium,
    link_client: LinkClient,
) -> None:
    condominium = create_condominium(name="Residencial Antigo")
    client_user = create_user(role=Role.CLIENT, email="cliente@example.com")
    link_client(client_user, condominium)
    operator = create_user(role=Role.OPERATOR, email="operador@example.com")

    response = db_client.patch(
        f"/condominiums/{condominium.id}",
        json={"name": "Residencial Atualizado"},
        headers=authenticate_as(operator),
    )

    assert response.status_code == 200
    assert len(recording_sender.messages) == 1
    assert "Residencial Atualizado" in recording_sender.messages[0].body
    logs = db_session.scalars(select(ClientNotificationLog)).all()
    assert len(logs) == 1
    assert logs[0].event_type == ClientNotificationEvent.CONDOMINIUM_UPDATED
    assert logs[0].user_id == client_user.id

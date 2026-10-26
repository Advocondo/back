import runpy
import sys
from contextlib import nullcontext
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import advocondo.common.clock
import advocondo.db
from advocondo.acordos.models import Agreement
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.notificacoes.models import Notification
from advocondo.notificacoes.overdue import notify_overdue_installments
from advocondo.users.models import Role, User, UserStatus
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.painel_cliente import CreateAgreementWithInstallments
from tests.fixtures.users import CreateUser
from tests.support.clock import FrozenClock

# O relógio dos testes está em 2 de março de 2026.
YESTERDAY = date(2026, 3, 1)
TODAY = date(2026, 3, 2)
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def count_notifications(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(Notification)) or 0


def notified_users(db_session: Session) -> set[str]:
    return {
        user.name
        for user in db_session.scalars(
            select(User).join(Notification, Notification.user_id == User.id)
        )
    }


def list_notifications(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get("/notifications", headers=headers)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
def mirante(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Residencial Mirante")


@pytest.fixture
def jose(create_debtor: CreateDebtor, mirante: Condominium) -> Debtor:
    return create_debtor(mirante, name="José Simão")


@pytest.fixture
def admin(create_user: CreateUser) -> User:
    return create_user(email="carla@example.com", name="Carla Admin", role=Role.ADMIN)


@pytest.fixture
def lawyer(create_user: CreateUser) -> User:
    return create_user(
        email="marina@example.com",
        name="Marina Dias",
        role=Role.OPERATOR,
        is_lawyer=True,
        oab_number="123456/DF",
    )


@pytest.fixture
def overdue_agreement(
    db_session: Session,
    create_agreement_with_installments: CreateAgreementWithInstallments,
    mirante: Condominium,
    jose: Debtor,
    lawyer: User,
) -> Agreement:
    """Acordo da Marina com a 1ª parcela vencida ontem e a 2ª vencendo hoje."""
    agreement = create_agreement_with_installments(
        mirante, jose, [(YESTERDAY, None), (TODAY, None)]
    )
    agreement.responsible_lawyer = lawyer
    db_session.flush()
    return agreement


class TestNotifyOverdueInstallments:
    def test_responsible_lawyer_and_administrator_are_notified(
        self,
        db_session: Session,
        clock: FrozenClock,
        admin: User,
        overdue_agreement: Agreement,
    ) -> None:
        """US30-CA01: só a 1ª parcela atrasou; a 2ª vence hoje (US27)."""
        created = notify_overdue_installments(db_session, clock)

        assert created == 2
        assert notified_users(db_session) == {"Carla Admin", "Marina Dias"}

    def test_running_again_does_not_repeat_notifications(
        self,
        db_session: Session,
        clock: FrozenClock,
        admin: User,
        overdue_agreement: Agreement,
    ) -> None:
        notify_overdue_installments(db_session, clock)

        assert notify_overdue_installments(db_session, clock) == 0
        assert count_notifications(db_session) == 2

    def test_installment_is_notified_the_day_after_its_due_date(
        self,
        db_session: Session,
        clock: FrozenClock,
        admin: User,
        overdue_agreement: Agreement,
    ) -> None:
        notify_overdue_installments(db_session, clock)
        clock.advance(timedelta(days=1))

        assert notify_overdue_installments(db_session, clock) == 2

    def test_paid_installment_is_not_notified(
        self,
        db_session: Session,
        clock: FrozenClock,
        admin: User,
        overdue_agreement: Agreement,
    ) -> None:
        first = overdue_agreement.installments[0]
        first.receive(first.amount, YESTERDAY)
        db_session.flush()

        assert notify_overdue_installments(db_session, clock) == 0

    def test_installment_of_cancelled_agreement_is_not_notified(
        self,
        db_session: Session,
        clock: FrozenClock,
        admin: User,
        overdue_agreement: Agreement,
    ) -> None:
        """As parcelas de acordo cancelado saem da cobrança (US20)."""
        overdue_agreement.cancel(reason=None, now=clock.now())
        db_session.flush()

        assert notify_overdue_installments(db_session, clock) == 0

    def test_partially_paid_installment_is_notified(
        self,
        db_session: Session,
        clock: FrozenClock,
        admin: User,
        overdue_agreement: Agreement,
    ) -> None:
        """Paga em parte, a parcela vencida continua atrasada (US28-CA01)."""
        first = overdue_agreement.installments[0]
        first.receive(first.amount / 2, YESTERDAY)
        db_session.flush()

        assert notify_overdue_installments(db_session, clock) == 2

    def test_inactive_administrator_is_not_notified(
        self,
        db_session: Session,
        clock: FrozenClock,
        create_user: CreateUser,
        admin: User,
        overdue_agreement: Agreement,
    ) -> None:
        create_user(
            email="ex@example.com",
            name="Ex Admin",
            role=Role.ADMIN,
            status=UserStatus.INACTIVE,
        )

        notify_overdue_installments(db_session, clock)

        assert notified_users(db_session) == {"Carla Admin", "Marina Dias"}

    def test_command_line_creates_the_notifications(
        self,
        db_session: Session,
        clock: FrozenClock,
        admin: User,
        overdue_agreement: Agreement,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Roda o módulo como `python -m advocondo.notificacoes.overdue` faz."""
        monkeypatch.setattr(
            advocondo.db, "get_sessionmaker", lambda: lambda: nullcontext(db_session)
        )
        monkeypatch.setattr(advocondo.common.clock, "get_clock", lambda: clock)
        # Importa de novo, como o interpretador faz ao rodar o módulo como script.
        monkeypatch.delitem(sys.modules, "advocondo.notificacoes.overdue")

        runpy.run_module("advocondo.notificacoes.overdue", run_name="__main__")

        assert count_notifications(db_session) == 2
        assert "2 notificações de parcela em atraso criadas." in capsys.readouterr().out


class TestNotificationRoutes:
    @pytest.fixture
    def notified(
        self,
        db_session: Session,
        clock: FrozenClock,
        admin: User,
        overdue_agreement: Agreement,
    ) -> None:
        notify_overdue_installments(db_session, clock)

    def test_user_sees_the_notification_with_the_unread_count(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        lawyer: User,
        overdue_agreement: Agreement,
        notified: None,
    ) -> None:
        """US30-CA01 e CA02: a notificação traz os ids da parcela e do acordo."""
        body = list_notifications(db_client, authenticate_as(lawyer))

        assert body["unread_count"] == 1
        [notification] = body["notifications"]
        installment = notification["installment"]
        assert notification["read_at"] is None
        assert installment["id"] == str(overdue_agreement.installments[0].id)
        assert installment["agreement_id"] == str(overdue_agreement.id)
        assert installment["number"] == 1
        assert installment["installment_count"] == 2
        assert installment["due_date"] == "2026-03-01"
        assert installment["remaining_amount"] == "100.00"
        assert installment["debtor"]["name"] == "José Simão"

    def test_user_does_not_see_notifications_of_others(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        notified: None,
    ) -> None:
        operator = create_user(email="bruno@example.com", role=Role.OPERATOR)

        body = list_notifications(db_client, authenticate_as(operator))

        assert body == {"unread_count": 0, "notifications": []}

    def test_opening_the_notification_marks_it_as_read(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        lawyer: User,
        notified: None,
    ) -> None:
        """US30-CA02"""
        headers = authenticate_as(lawyer)
        [notification] = list_notifications(db_client, headers)["notifications"]

        response = db_client.post(
            f"/notifications/{notification['id']}/read", headers=headers
        )

        assert response.status_code == 200
        assert response.json()["read_at"] is not None
        assert list_notifications(db_client, headers)["unread_count"] == 0

    def test_all_notifications_can_be_marked_as_read(
        self,
        db_client: TestClient,
        db_session: Session,
        clock: FrozenClock,
        authenticate_as: AuthenticateAs,
        admin: User,
        notified: None,
    ) -> None:
        clock.advance(timedelta(days=1))
        notify_overdue_installments(db_session, clock)
        headers = authenticate_as(admin)

        response = db_client.post("/notifications/read", headers=headers)

        body = list_notifications(db_client, headers)
        assert response.status_code == 204
        assert body["unread_count"] == 0
        assert len(body["notifications"]) == 2

    def test_newest_notification_comes_first(
        self,
        db_client: TestClient,
        db_session: Session,
        clock: FrozenClock,
        authenticate_as: AuthenticateAs,
        admin: User,
        notified: None,
    ) -> None:
        clock.advance(timedelta(days=1))
        notify_overdue_installments(db_session, clock)

        body = list_notifications(db_client, authenticate_as(admin))

        assert [item["installment"]["number"] for item in body["notifications"]] == [
            2,
            1,
        ]

    def test_notification_of_another_user_is_not_found(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        lawyer: User,
        notified: None,
    ) -> None:
        """Não revela que a notificação de outro usuário existe."""
        lawyer_headers = authenticate_as(lawyer)
        [notification] = list_notifications(db_client, lawyer_headers)["notifications"]
        operator = create_user(email="bruno@example.com", role=Role.OPERATOR)

        response = db_client.post(
            f"/notifications/{notification['id']}/read",
            headers=authenticate_as(operator),
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Notificação não encontrada."

    def test_unknown_notification_is_not_found(
        self, db_client: TestClient, authenticate_as: AuthenticateAs, lawyer: User
    ) -> None:
        response = db_client.post(
            f"/notifications/{UNKNOWN_ID}/read", headers=authenticate_as(lawyer)
        )

        assert response.status_code == 404

    def test_anonymous_user_is_refused(self, db_client: TestClient) -> None:
        assert db_client.get("/notifications").status_code == 401

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement, AgreementEditField, AgreementEditLog
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.parcelas.models import InstallmentChange, InstallmentChangeLog
from advocondo.users.models import AuditAction, Role, User, UserAuditLog
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.painel_cliente import CreateAgreementWithInstallments
from tests.fixtures.users import CreateUser

pytestmark = pytest.mark.integration

# Horários em UTC. Brasília fica 3 horas atrás.
MARCH_2_NOON = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
# 01:00 de 3 de março em UTC ainda é 22:00 de 2 de março em Brasília.
MARCH_2_LATE_NIGHT = datetime(2026, 3, 3, 1, 0, tzinfo=UTC)
MARCH_4_MORNING = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def admin(create_user: CreateUser) -> User:
    return create_user(email="carla@example.com", name="Carla Admin", role=Role.ADMIN)


@pytest.fixture
def operator(create_user: CreateUser) -> User:
    return create_user(
        email="marina@example.com", name="Marina Dias", role=Role.OPERATOR
    )


@pytest.fixture
def client_user(create_user: CreateUser) -> User:
    return create_user(
        email="sindico@example.com", name="Paulo Síndico", role=Role.CLIENT
    )


@pytest.fixture
def mirante(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Residencial Mirante")


@pytest.fixture
def jose(create_debtor: CreateDebtor, mirante: Condominium) -> Debtor:
    return create_debtor(mirante, name="José Simão")


@pytest.fixture
def agreement(
    create_agreement_with_installments: CreateAgreementWithInstallments,
    mirante: Condominium,
    jose: Debtor,
) -> Agreement:
    return create_agreement_with_installments(
        mirante, jose, [(date(2026, 3, 1), None), (date(2026, 4, 1), None)]
    )


@pytest.fixture
def trail(
    db_session: Session,
    admin: User,
    operator: User,
    client_user: User,
    mirante: Condominium,
    agreement: Agreement,
) -> None:
    """Uma ação de cada registro, em dias diferentes: a baixa da Marina, a edição do
    acordo pela Carla e o vínculo do Cliente com o condomínio, também pela Carla."""
    db_session.add_all(
        [
            InstallmentChangeLog(
                installment_id=agreement.installments[0].id,
                changed_by_id=operator.id,
                changed_at=MARCH_2_NOON,
                change=InstallmentChange.PAYMENT_RECORDED,
                old_value=None,
                new_value="150.00",
            ),
            AgreementEditLog(
                agreement_id=agreement.id,
                edited_by_id=admin.id,
                edited_at=MARCH_2_LATE_NIGHT,
                field=AgreementEditField.TOTAL_AMOUNT,
                old_value="300.00",
                new_value="350.00",
                had_paid_installments=True,
            ),
            UserAuditLog(
                user_id=client_user.id,
                actor_id=admin.id,
                action=AuditAction.CONDOMINIUMS_CHANGED,
                old_value=None,
                new_value=None,
                details={
                    "added": [{"id": str(mirante.id), "name": mirante.name}],
                    "removed": [],
                },
                created_at=MARCH_4_MORNING,
            ),
        ]
    )
    db_session.flush()


def get_trail(
    db_client: TestClient, headers: dict[str, str], **params: Any
) -> dict[str, Any]:
    response = db_client.get("/audit", headers=headers, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def actions(body: dict[str, Any]) -> list[str]:
    return [entry["action"] for entry in body["entries"]]


@pytest.mark.usefixtures("trail")
class TestAuditTrail:
    def test_admin_sees_every_action_newest_first(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        admin: User,
        operator: User,
        client_user: User,
        mirante: Condominium,
        jose: Debtor,
        agreement: Agreement,
    ) -> None:
        """CA01: ações de acordos, parcelas e usuários, da mais recente para a mais antiga."""
        body = get_trail(db_client, authenticate_as(admin))

        assert body["total"] == 3
        user_entry, agreement_entry, installment_entry = body["entries"]
        assert user_entry == {
            "id": user_entry["id"],
            "occurred_at": "2026-03-04T12:00:00Z",
            "category": "users",
            "action": "condominiums_changed",
            "actor": {"id": str(admin.id), "name": "Carla Admin"},
            "old_value": None,
            "new_value": None,
            "agreement": None,
            "installment_number": None,
            "field": None,
            "target_user": {"id": str(client_user.id), "name": "Paulo Síndico"},
            "added_condominiums": [
                {"id": str(mirante.id), "name": "Residencial Mirante"}
            ],
            "removed_condominiums": [],
        }
        expected_agreement = {
            "id": str(agreement.id),
            "debtor": {"id": str(jose.id), "name": "José Simão", "unit": jose.unit},
            "condominium": {"id": str(mirante.id), "name": "Residencial Mirante"},
        }
        assert agreement_entry["category"] == "financial"
        assert agreement_entry["action"] == "agreement_edited"
        assert agreement_entry["field"] == "total_amount"
        assert agreement_entry["agreement"] == expected_agreement
        assert (agreement_entry["old_value"], agreement_entry["new_value"]) == (
            "300.00",
            "350.00",
        )
        assert installment_entry["action"] == "payment_recorded"
        assert installment_entry["actor"] == {
            "id": str(operator.id),
            "name": "Marina Dias",
        }
        assert installment_entry["installment_number"] == 1
        assert installment_entry["agreement"] == expected_agreement
        assert installment_entry["target_user"] is None

    def test_filters_by_author(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        admin: User,
        operator: User,
    ) -> None:
        body = get_trail(db_client, authenticate_as(admin), actor_id=str(operator.id))
        assert body["total"] == 1
        assert actions(body) == ["payment_recorded"]

    def test_filters_by_category(
        self, db_client: TestClient, authenticate_as: AuthenticateAs, admin: User
    ) -> None:
        headers = authenticate_as(admin)
        assert actions(get_trail(db_client, headers, category="financial")) == [
            "agreement_edited",
            "payment_recorded",
        ]
        assert actions(get_trail(db_client, headers, category="users")) == [
            "condominiums_changed"
        ]

    def test_period_uses_the_day_in_brazil(
        self, db_client: TestClient, authenticate_as: AuthenticateAs, admin: User
    ) -> None:
        """A edição às 22h de 2 de março em Brasília já é dia 3 em UTC, e conta no dia 2."""
        headers = authenticate_as(admin)
        march_2 = get_trail(
            db_client, headers, date_from="2026-03-02", date_to="2026-03-02"
        )
        assert actions(march_2) == ["agreement_edited", "payment_recorded"]
        assert get_trail(db_client, headers, date_from="2026-03-03")["total"] == 1
        assert get_trail(db_client, headers, date_to="2026-03-01")["total"] == 0

    def test_filters_combine(
        self, db_client: TestClient, authenticate_as: AuthenticateAs, admin: User
    ) -> None:
        """CA02: autor, período e tipo juntos."""
        body = get_trail(
            db_client,
            authenticate_as(admin),
            actor_id=str(admin.id),
            category="financial",
            date_from="2026-03-02",
            date_to="2026-03-03",
        )
        assert actions(body) == ["agreement_edited"]

    def test_paginates_and_keeps_the_total(
        self, db_client: TestClient, authenticate_as: AuthenticateAs, admin: User
    ) -> None:
        headers = authenticate_as(admin)
        first = get_trail(db_client, headers, limit=2)
        second = get_trail(db_client, headers, limit=2, offset=2)
        assert (first["total"], second["total"]) == (3, 3)
        assert actions(first) == ["condominiums_changed", "agreement_edited"]
        assert actions(second) == ["payment_recorded"]

    def test_start_after_end_is_refused(
        self, db_client: TestClient, authenticate_as: AuthenticateAs, admin: User
    ) -> None:
        response = db_client.get(
            "/audit",
            headers=authenticate_as(admin),
            params={"date_from": "2026-03-04", "date_to": "2026-03-02"},
        )
        assert response.status_code == 422
        assert (
            response.json()["detail"]
            == "A data inicial não pode ser depois da data final."
        )

    def test_unknown_category_is_refused(
        self, db_client: TestClient, authenticate_as: AuthenticateAs, admin: User
    ) -> None:
        response = db_client.get(
            "/audit", headers=authenticate_as(admin), params={"category": "x"}
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("role", [Role.OPERATOR, Role.CLIENT])
    def test_other_roles_are_forbidden(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        create_user: CreateUser,
        role: Role,
    ) -> None:
        """CA03: só o Administrador vê a trilha."""
        user = create_user(email=f"{role}@example.com", role=role)
        assert db_client.get("/audit", headers=authenticate_as(user)).status_code == 403

    def test_requires_login(self, db_client: TestClient) -> None:
        assert db_client.get("/audit").status_code == 401


def test_action_without_author_comes_with_null_actor(
    db_client: TestClient,
    db_session: Session,
    authenticate_as: AuthenticateAs,
    admin: User,
    client_user: User,
) -> None:
    """Quem fez a ação pode ter sido removido: o registro fica, sem autor."""
    db_session.add(
        UserAuditLog(
            user_id=client_user.id,
            actor_id=None,
            action=AuditAction.STATUS_CHANGED,
            old_value="active",
            new_value="inactive",
            created_at=MARCH_2_NOON,
        )
    )
    db_session.flush()

    entry = get_trail(db_client, authenticate_as(admin))["entries"][0]
    assert entry["actor"] is None
    assert (entry["old_value"], entry["new_value"]) == ("active", "inactive")


def test_empty_trail(
    db_client: TestClient, authenticate_as: AuthenticateAs, admin: User
) -> None:
    assert get_trail(db_client, authenticate_as(admin)) == {"total": 0, "entries": []}

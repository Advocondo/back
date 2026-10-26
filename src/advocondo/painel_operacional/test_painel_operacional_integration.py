from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from advocondo.condominios.models import Condominium
from advocondo.users.models import Role, User
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.metas import CreateGoal
from tests.fixtures.painel_cliente import CreateAgreementWithInstallments
from tests.fixtures.users import CreateUser

URL = "/operator-panel/financial"
# O relógio dos testes está em 2 de março de 2026: o período é março.


@pytest.fixture
def mirante(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Residencial Mirante")


@pytest.fixture
def ana(create_user: CreateUser) -> User:
    return create_user(email="ana@example.com", name="Ana", role=Role.OPERATOR)


@pytest.fixture
def bruno(create_user: CreateUser) -> User:
    return create_user(email="bruno@example.com", name="Bruno", role=Role.OPERATOR)


@pytest.fixture
def portfolio(
    db_session: Session,
    create_agreement_with_installments: CreateAgreementWithInstallments,
    create_debtor: CreateDebtor,
    mirante: Condominium,
    ana: User,
    bruno: User,
) -> None:
    """Parcelas de R$ 100,00 com R$ 10,00 de honorários cada.

    - Ana: duas pagas em março (uma venceu em fevereiro), uma paga em fevereiro e
      uma em aberto. A comissão de março é R$ 20,00.
    - Bruno: uma paga em março, R$ 10,00.
    - Acordo sem responsável: uma paga em março, que não é de ninguém.
    """
    of_ana = create_agreement_with_installments(
        mirante,
        create_debtor(mirante, name="José"),
        [
            (date(2026, 1, 10), date(2026, 2, 15)),
            (date(2026, 2, 10), date(2026, 3, 1)),
            (date(2026, 3, 10), date(2026, 3, 2)),
            (date(2026, 3, 31), None),
        ],
    )
    of_ana.responsible_lawyer_id = ana.id
    of_bruno = create_agreement_with_installments(
        mirante,
        create_debtor(mirante, name="Maria"),
        [(date(2026, 3, 1), date(2026, 3, 1))],
    )
    of_bruno.responsible_lawyer_id = bruno.id
    create_agreement_with_installments(
        mirante,
        create_debtor(mirante, name="Paulo"),
        [(date(2026, 3, 1), date(2026, 3, 2))],
    )
    db_session.flush()


class TestOperatorFinancialSummary:
    def test_operator_sees_only_their_own_commission_of_the_month(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        create_goal: CreateGoal,
        ana: User,
        portfolio: None,
    ) -> None:
        """US32-CA01: a meta é a do mês, definida pelo Administrador (US36)."""
        create_goal(ana, 2026, 3, Decimal("100.00"))

        response = db_client.get(URL, headers=authenticate_as(ana))

        assert response.status_code == 200
        assert response.json() == {
            "goal": "100.00",
            "accumulated_commission": "20.00",
            "remaining_to_goal": "80.00",
            "period": {"month": 3, "year": 2026},
        }

    def test_goal_already_reached_leaves_nothing_remaining(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        create_goal: CreateGoal,
        ana: User,
        portfolio: None,
    ) -> None:
        """US32-CA01: a comissão acima da meta não deixa saldo negativo."""
        create_goal(ana, 2026, 3, Decimal("15.00"))

        body = db_client.get(URL, headers=authenticate_as(ana)).json()

        assert body["accumulated_commission"] == "20.00"
        assert body["remaining_to_goal"] == "0.00"

    def test_operator_without_agreements_has_no_commission(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        create_user: CreateUser,
        portfolio: None,
    ) -> None:
        carla = create_user(email="carla@example.com", role=Role.OPERATOR)

        body = db_client.get(URL, headers=authenticate_as(carla)).json()

        assert body["accumulated_commission"] == "0.00"

    def test_without_a_goal_for_the_month_the_goal_is_empty(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        create_goal: CreateGoal,
        ana: User,
        portfolio: None,
    ) -> None:
        """US32-CA01: a meta de outro mês não vale para o mês atual."""
        create_goal(ana, 2026, 2, Decimal("100.00"))

        body = db_client.get(URL, headers=authenticate_as(ana)).json()

        assert body["goal"] is None
        assert body["remaining_to_goal"] is None
        assert body["accumulated_commission"] == "20.00"

    def test_goal_defined_by_the_admin_shows_up_in_the_panel(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        create_user: CreateUser,
        ana: User,
    ) -> None:
        """US32 e US36: a meta definida pela rota da US36 é a que o painel mostra."""
        admin = create_user(email="admin@example.com", role=Role.ADMIN)
        defined = db_client.put(
            f"/users/{ana.id}/goals/2026/3",
            json={"target_amount": "250.00"},
            headers=authenticate_as(admin),
        )

        body = db_client.get(URL, headers=authenticate_as(ana)).json()

        assert defined.status_code == 200
        assert body["goal"] == "250.00"
        assert body["remaining_to_goal"] == "250.00"

    def test_no_office_total_nor_other_members_data(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        bruno: User,
        portfolio: None,
    ) -> None:
        """US32-CA02"""
        body = db_client.get(URL, headers=authenticate_as(bruno)).json()

        assert set(body) == {
            "goal",
            "accumulated_commission",
            "remaining_to_goal",
            "period",
        }
        assert body["accumulated_commission"] == "10.00"

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.ADMIN, id="admin"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_panel_is_only_for_the_operational_team(
        self,
        db_client: TestClient,
        authenticate_as: AuthenticateAs,
        create_user: CreateUser,
        role: Role,
    ) -> None:
        """US32-CA02"""
        user = create_user(email="outro@example.com", role=role)

        response = db_client.get(URL, headers=authenticate_as(user))

        assert response.status_code == 403

    def test_requires_a_session(self, db_client: TestClient) -> None:
        assert db_client.get(URL).status_code == 401

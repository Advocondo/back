import pytest
from fastapi.testclient import TestClient

from advocondo.users.models import Role, UserStatus
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.users import CreateUser


@pytest.fixture
def admin_headers(
    create_user: CreateUser, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(
        create_user(email="admin@example.com", name="Zuleide Admin", role=Role.ADMIN)
    )


class TestSearchUsers:
    def test_lists_every_role_and_status_by_name(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        admin_headers: dict[str, str],
    ) -> None:
        create_user(email="bia@example.com", name="Bia", role=Role.CLIENT)
        create_user(email="ana@example.com", name="Ana", status=UserStatus.INACTIVE)
        create_user(email="caio@example.com", name="Caio", status=UserStatus.PENDING)

        response = db_client.get("/users", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        assert [user["name"] for user in body] == [
            "Ana",
            "Bia",
            "Caio",
            "Zuleide Admin",
        ]
        assert set(body[0]) == {
            "id",
            "name",
            "email",
            "role",
            "status",
            "is_lawyer",
            "oab_number",
        }
        assert body[0]["status"] == "inactive"

    @pytest.mark.parametrize(
        ("search", "expected"),
        [
            pytest.param("ANA", ["Ana Lima"], id="part-of-the-name-ignoring-case"),
            pytest.param("@escritorio", ["Bia Souza"], id="part-of-the-email"),
            pytest.param("%", [], id="percent-sign-is-searched-literally"),
            pytest.param("_", ["Caio Dias"], id="underscore-is-searched-literally"),
        ],
    )
    def test_searches_by_name_or_email(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        admin_headers: dict[str, str],
        search: str,
        expected: list[str],
    ) -> None:
        create_user(email="ana@example.com", name="Ana Lima")
        create_user(email="bia@escritorio.com", name="Bia Souza")
        create_user(email="caio_dias@example.com", name="Caio Dias")

        response = db_client.get(
            "/users", params={"search": search}, headers=admin_headers
        )

        assert [user["name"] for user in response.json()] == expected

    def test_paginates(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        admin_headers: dict[str, str],
    ) -> None:
        create_user(email="ana@example.com", name="Ana")
        create_user(email="bia@example.com", name="Bia")

        response = db_client.get(
            "/users", params={"limit": 1, "offset": 1}, headers=admin_headers
        )

        assert [user["name"] for user in response.json()] == ["Bia"]

    def test_refuses_a_limit_above_the_maximum(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = db_client.get("/users", params={"limit": 201}, headers=admin_headers)

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.OPERATOR, id="operator"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_only_the_administrator_lists_users(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        """US07-CA02"""
        headers = authenticate_as(create_user(role=role))

        response = db_client.get("/users", headers=headers)

        assert response.status_code == 403

    def test_requires_a_session(self, db_client: TestClient) -> None:
        assert db_client.get("/users").status_code == 401

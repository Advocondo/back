import getpass
import runpy
import sys
from collections.abc import Iterator
from contextlib import nullcontext
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import advocondo.db
from advocondo.users.create_admin import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    ReadPassword,
    create_admin,
    parse_arguments,
)
from advocondo.users.models import Role, User, UserStatus
from tests.fixtures.users import CreateUser

PASSWORD = "senha-do-admin"


def typed_passwords(*passwords: str) -> ReadPassword:
    answers: Iterator[str] = iter(passwords)
    return lambda prompt: next(answers)


def run_create_admin(
    session: Session,
    email: str = "ana@example.com",
    passwords: tuple[str, str] = (PASSWORD, PASSWORD),
) -> int:
    arguments = parse_arguments(["--email", email, "--name", "Ana Souza"])
    return create_admin(arguments, session, typed_passwords(*passwords))


def count_users(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(User)) or 0


def build_user(**overrides: Any) -> User:
    fields: dict[str, Any] = {
        "email": "ana@example.com",
        "name": "Ana Souza",
        "role": Role.OPERATOR,
        "status": UserStatus.ACTIVE,
        "password_hash": "hash",
    }
    return User(**(fields | overrides))


class TestCreateAdmin:
    def test_first_admin_is_created_active_and_can_log_in(
        self, db_client: TestClient, db_session: Session
    ) -> None:
        exit_code = run_create_admin(db_session, email="Ana@Example.com")

        response = db_client.post(
            "/auth/login", json={"email": "ana@example.com", "password": PASSWORD}
        )
        assert exit_code == EXIT_SUCCESS
        assert response.status_code == 200
        assert response.json()["user"]["role"] == Role.ADMIN.value

    def test_first_admin_is_stored_as_active_administrator(
        self, db_session: Session
    ) -> None:
        run_create_admin(db_session)

        user = db_session.scalars(select(User)).one()
        assert (user.email, user.role, user.status) == (
            "ana@example.com",
            Role.ADMIN,
            UserStatus.ACTIVE,
        )

    def test_admin_is_not_created_when_a_user_already_exists(
        self,
        db_session: Session,
        create_user: CreateUser,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        create_user(email="existente@example.com")

        exit_code = run_create_admin(db_session)

        assert exit_code == EXIT_FAILURE
        assert count_users(db_session) == 1
        assert "Os demais entram por convite." in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("email", "passwords", "message"),
        [
            pytest.param(
                "ana-sem-arroba",
                (PASSWORD, PASSWORD),
                "E-mail inválido",
                id="bad-email",
            ),
            pytest.param(
                "ana@example.com",
                (PASSWORD, "outra-senha"),
                "As senhas não conferem.",
                id="confirmation-mismatch",
            ),
            pytest.param(
                "ana@example.com",
                ("curta", "curta"),
                "pelo menos 8 caracteres",
                id="password-too-short",
            ),
        ],
    )
    def test_admin_is_not_created_with_invalid_input(
        self,
        db_session: Session,
        capsys: pytest.CaptureFixture[str],
        email: str,
        passwords: tuple[str, str],
        message: str,
    ) -> None:
        exit_code = run_create_admin(db_session, email=email, passwords=passwords)

        assert exit_code == EXIT_FAILURE
        assert count_users(db_session) == 0
        assert message in capsys.readouterr().err

    def test_command_line_creates_the_admin_and_exits_successfully(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Runs the module as `python -m advocondo.users.create_admin` does."""
        monkeypatch.setattr(
            sys, "argv", ["create_admin", "--email", "ana@example.com", "--name", "Ana"]
        )
        monkeypatch.setattr(getpass, "getpass", typed_passwords(PASSWORD, PASSWORD))
        monkeypatch.setattr(
            advocondo.db, "get_sessionmaker", lambda: lambda: nullcontext(db_session)
        )
        # A fresh import, as the interpreter does when running the module as a script.
        monkeypatch.delitem(sys.modules, "advocondo.users.create_admin")

        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("advocondo.users.create_admin", run_name="__main__")

        assert exit_info.value.code == EXIT_SUCCESS
        assert count_users(db_session) == 1


class TestUserModel:
    def test_new_user_starts_pending_with_generated_id_and_timestamps(
        self,
        db_session: Session,
    ) -> None:
        user = User(email="ana@example.com", name="Ana Souza", role=Role.OPERATOR)

        db_session.add(user)
        db_session.flush()

        assert user.status == UserStatus.PENDING
        assert user.id is not None
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_email_is_unique(self, db_session: Session) -> None:
        db_session.add(build_user(email="ana@example.com"))
        db_session.flush()

        db_session.add(build_user(email="ana@example.com", name="Outra Ana"))

        with pytest.raises(IntegrityError, match="uq_users_email"):
            db_session.flush()

    def test_email_must_be_stored_lowercase(self, db_session: Session) -> None:
        db_session.add(build_user(email="Ana@Example.com"))

        with pytest.raises(IntegrityError, match="ck_users_email_is_lowercase"):
            db_session.flush()

    def test_active_user_must_have_a_password(self, db_session: Session) -> None:
        db_session.add(build_user(status=UserStatus.ACTIVE, password_hash=None))

        with pytest.raises(IntegrityError, match="ck_users_active_user_has_password"):
            db_session.flush()

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(UserStatus.PENDING, id="pending-invite"),
            pytest.param(UserStatus.INACTIVE, id="inactive"),
        ],
    )
    def test_user_that_is_not_active_may_have_no_password(
        self, db_session: Session, status: UserStatus
    ) -> None:
        db_session.add(build_user(status=status, password_hash=None))
        db_session.flush()

        assert db_session.scalar(select(User.status)) == status

import getpass
import runpy
import sys
from collections.abc import Iterator
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
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


def test_first_admin_is_created_active_and_can_log_in(
    db_client: TestClient, db_session: Session
) -> None:
    exit_code = run_create_admin(db_session, email="Ana@Example.com")

    response = db_client.post(
        "/auth/login", json={"email": "ana@example.com", "password": PASSWORD}
    )
    assert exit_code == EXIT_SUCCESS
    assert response.status_code == 200
    assert response.json()["user"]["role"] == Role.ADMIN.value


def test_first_admin_is_stored_as_active_administrator(db_session: Session) -> None:
    run_create_admin(db_session)

    user = db_session.scalars(select(User)).one()
    assert (user.email, user.role, user.status) == (
        "ana@example.com",
        Role.ADMIN,
        UserStatus.ACTIVE,
    )


def test_admin_is_not_created_when_a_user_already_exists(
    db_session: Session, create_user: CreateUser, capsys: pytest.CaptureFixture[str]
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
            "ana-sem-arroba", (PASSWORD, PASSWORD), "E-mail inválido", id="bad-email"
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
    db_session: Session, monkeypatch: pytest.MonkeyPatch
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

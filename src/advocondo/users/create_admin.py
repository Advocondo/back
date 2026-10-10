"""Creates the first user, an Administrator, who then invites everyone else (US07).

Run once after the first deploy, in a terminal of the API container:

    python -m advocondo.users.create_admin --email ana@example.com --name "Ana Souza"

The password is typed in the terminal, so it never shows up in the shell history.
"""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from advocondo.common.errors import AppError
from advocondo.common.passwords import get_password_hasher
from advocondo.db import get_sessionmaker
from advocondo.users.repository import UserRepository
from advocondo.users.service import UserService

ReadPassword = Callable[[str], str]

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria o primeiro usuário do sistema, com perfil Administrador."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    return parser.parse_args(argv)


def create_admin(
    arguments: argparse.Namespace, session: Session, read_password: ReadPassword
) -> int:
    try:
        email = TypeAdapter(EmailStr).validate_python(arguments.email)
    except ValidationError:
        return fail(f"E-mail inválido: {arguments.email}")

    password = read_password("Senha: ")
    if read_password("Confirme a senha: ") != password:
        return fail("As senhas não conferem.")

    service = UserService(session, UserRepository(session), get_password_hasher())
    try:
        user = service.create_first_admin(email, arguments.name, password)
    except AppError as error:
        return fail(error.message)

    print(f"Administrador {user.email} criado. Já é possível fazer login.")
    return EXIT_SUCCESS


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return EXIT_FAILURE


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    with get_sessionmaker()() as session:
        return create_admin(arguments, session, getpass.getpass)


if __name__ == "__main__":
    sys.exit(main())

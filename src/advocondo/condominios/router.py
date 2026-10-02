from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, status
from sqlalchemy.orm import Session

from advocondo.auth import require_user
from advocondo.condominios import service
from advocondo.condominios.exceptions import (
    CnpjAlreadyRegisteredError,
    CondominioNotFoundError,
    InvalidContractDatesError,
)
from advocondo.condominios.models import Condominio
from advocondo.condominios.schemas import (
    CondominioCreate,
    CondominioRead,
    CondominioUpdate,
)
from advocondo.db import get_session
from advocondo.errors import register_error

router = APIRouter(
    prefix="/condominios",
    tags=["condominios"],
    dependencies=[Depends(require_user)],
)

SessionDep = Annotated[Session, Depends(get_session)]


def register_errors(app: FastAPI) -> None:
    """Exceções de negócio do módulo -> respostas HTTP (chamado em `create_app`)."""
    register_error(
        app,
        CondominioNotFoundError,
        status.HTTP_404_NOT_FOUND,
        "Condomínio não encontrado.",
    )
    register_error(
        app,
        CnpjAlreadyRegisteredError,
        status.HTTP_409_CONFLICT,
        "Já existe um condomínio com este CNPJ.",
    )
    register_error(
        app,
        InvalidContractDatesError,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [
            {
                "type": "value_error",
                "loc": ["body", "contrato_renovacao"],
                "msg": "A data de renovação não pode ser anterior ao início do contrato.",
            }
        ],
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CondominioRead)
def create_condominio(data: CondominioCreate, session: SessionDep) -> Condominio:
    return service.create(session, data)


@router.get("", response_model=list[CondominioRead])
def list_condominios(
    session: SessionDep,
    q: Annotated[
        str | None, Query(description="Nome do condomínio ou do síndico")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[Condominio]:
    return service.search(session, q=q, limit=limit, offset=offset)


@router.get("/{condominio_id}", response_model=CondominioRead)
def get_condominio(condominio_id: int, session: SessionDep) -> Condominio:
    return service.get(session, condominio_id)


@router.patch("/{condominio_id}", response_model=CondominioRead)
def update_condominio(
    condominio_id: int, data: CondominioUpdate, session: SessionDep
) -> Condominio:
    return service.update(session, condominio_id, data)

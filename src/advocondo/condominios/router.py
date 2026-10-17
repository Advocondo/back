import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from advocondo.auth.dependencies import require_office_staff
from advocondo.condominios.dependencies import get_condominium_service
from advocondo.condominios.schemas import (
    CondominiumCreateRequest,
    CondominiumResponse,
    CondominiumUpdateRequest,
)
from advocondo.condominios.service import CondominiumService

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

router = APIRouter(
    prefix="/condominiums",
    tags=["condominiums"],
    dependencies=[Depends(require_office_staff)],
)

CondominiumServiceDependency = Annotated[
    CondominiumService, Depends(get_condominium_service)
]


@router.post("", status_code=status.HTTP_201_CREATED)
def register_condominium(
    request: CondominiumCreateRequest,
    condominium_service: CondominiumServiceDependency,
) -> CondominiumResponse:
    condominium = condominium_service.register(request)
    return CondominiumResponse.model_validate(condominium)


@router.get("")
def search_condominiums(
    condominium_service: CondominiumServiceDependency,
    search: Annotated[
        str | None, Query(description="Parte do nome do condomínio ou do síndico")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CondominiumResponse]:
    condominiums = condominium_service.search(search, limit, offset)
    return [CondominiumResponse.model_validate(item) for item in condominiums]


@router.get("/{condominium_id}")
def get_condominium(
    condominium_id: uuid.UUID, condominium_service: CondominiumServiceDependency
) -> CondominiumResponse:
    condominium = condominium_service.get(condominium_id)
    return CondominiumResponse.model_validate(condominium)


@router.patch("/{condominium_id}")
def update_condominium(
    condominium_id: uuid.UUID,
    request: CondominiumUpdateRequest,
    condominium_service: CondominiumServiceDependency,
) -> CondominiumResponse:
    condominium = condominium_service.update(condominium_id, request)
    return CondominiumResponse.model_validate(condominium)

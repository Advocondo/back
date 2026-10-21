import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from advocondo.auth.dependencies import require_office_staff
from advocondo.common.dependencies import Today
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


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=CondominiumResponse
)
def register_condominium(
    request: CondominiumCreateRequest,
    condominium_service: CondominiumServiceDependency,
    today: Today,
) -> CondominiumResponse:
    condominium = condominium_service.register(request)
    return CondominiumResponse.from_condominium(condominium, today)


@router.get("", response_model=list[CondominiumResponse])
def search_condominiums(
    condominium_service: CondominiumServiceDependency,
    today: Today,
    search: Annotated[
        str | None, Query(description="Parte do nome do condomínio ou do síndico")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CondominiumResponse]:
    condominiums = condominium_service.search(search, limit, offset)
    return [CondominiumResponse.from_condominium(item, today) for item in condominiums]


@router.get("/{condominium_id}", response_model=CondominiumResponse)
def get_condominium(
    condominium_id: uuid.UUID,
    condominium_service: CondominiumServiceDependency,
    today: Today,
) -> CondominiumResponse:
    condominium = condominium_service.get(condominium_id)
    if not condominium:
        raise HTTPException(status_code=404, detail="Condomínio não encontrado.")
    return CondominiumResponse.from_condominium(condominium, today)


@router.patch("/{condominium_id}", response_model=CondominiumResponse)
def update_condominium(
    condominium_id: uuid.UUID,
    request: CondominiumUpdateRequest,
    condominium_service: CondominiumServiceDependency,
    today: Today,
) -> CondominiumResponse:
    condominium = condominium_service.update(condominium_id, request)
    if not condominium:
        raise HTTPException(status_code=404, detail="Condomínio não encontrado.")
    return CondominiumResponse.from_condominium(condominium, today)

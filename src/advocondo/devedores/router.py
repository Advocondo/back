import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from advocondo.auth.dependencies import require_office_staff
from advocondo.devedores.dependencies import get_debtor_service
from advocondo.devedores.errors import SimilarDebtorsFoundError
from advocondo.devedores.schemas import (
    DebtorCreateRequest,
    DebtorResponse,
    DebtorUpdateRequest,
    SimilarDebtorsResponse,
)
from advocondo.devedores.service import DebtorService

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

router = APIRouter(
    prefix="/debtors",
    tags=["debtors"],
    dependencies=[Depends(require_office_staff)],
)

DebtorServiceDependency = Annotated[DebtorService, Depends(get_debtor_service)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DebtorResponse,
    responses={status.HTTP_409_CONFLICT: {"model": SimilarDebtorsResponse}},
)
def register_debtor(
    request: DebtorCreateRequest, debtor_service: DebtorServiceDependency
) -> DebtorResponse | JSONResponse:
    try:
        debtor = debtor_service.register(request)
    except SimilarDebtorsFoundError as warning:
        # Unlike other errors, the answer carries the similar debtors to show the user.
        return similar_debtors_response(warning)
    return DebtorResponse.model_validate(debtor)


@router.get("")
def search_debtors(
    debtor_service: DebtorServiceDependency,
    condominium_id: uuid.UUID | None = None,
    search: Annotated[
        str | None, Query(description="Parte do nome ou da unidade do devedor")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DebtorResponse]:
    debtors = debtor_service.search(condominium_id, search, limit, offset)
    return [DebtorResponse.model_validate(debtor) for debtor in debtors]


@router.get("/{debtor_id}")
def get_debtor(
    debtor_id: uuid.UUID, debtor_service: DebtorServiceDependency
) -> DebtorResponse:
    return DebtorResponse.model_validate(debtor_service.get(debtor_id))


@router.patch("/{debtor_id}")
def update_debtor(
    debtor_id: uuid.UUID,
    request: DebtorUpdateRequest,
    debtor_service: DebtorServiceDependency,
) -> DebtorResponse:
    return DebtorResponse.model_validate(debtor_service.update(debtor_id, request))


def similar_debtors_response(warning: SimilarDebtorsFoundError) -> JSONResponse:
    body = SimilarDebtorsResponse(
        detail=warning.message,
        similar_debtors=[
            DebtorResponse.model_validate(debtor) for debtor in warning.similar_debtors
        ],
    )
    return JSONResponse(
        body.model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT
    )

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from advocondo.auth.dependencies import require_office_staff
from advocondo.devedores.dependencies import get_debtor_service
from advocondo.devedores.errors import SimilarDebtorsFoundError
from advocondo.devedores.schemas import (
    DebtorCreateRequest,
    DebtorResponse,
    SimilarDebtorsResponse,
)
from advocondo.devedores.service import DebtorService

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

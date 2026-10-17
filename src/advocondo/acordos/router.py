import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from advocondo.acordos.dependencies import get_agreement_service
from advocondo.acordos.models import AgreementStatus
from advocondo.acordos.repository import AgreementFilters
from advocondo.acordos.schemas import AgreementCreateRequest, AgreementResponse
from advocondo.acordos.service import AgreementService
from advocondo.auth.dependencies import require_office_staff

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

router = APIRouter(
    prefix="/agreements",
    tags=["agreements"],
    dependencies=[Depends(require_office_staff)],
)

AgreementServiceDependency = Annotated[AgreementService, Depends(get_agreement_service)]


@router.post("", status_code=status.HTTP_201_CREATED)
def register_agreement(
    request: AgreementCreateRequest, agreement_service: AgreementServiceDependency
) -> AgreementResponse:
    return AgreementResponse.model_validate(agreement_service.register(request))


@router.get("")
def search_agreements(
    agreement_service: AgreementServiceDependency,
    agreement_status: Annotated[AgreementStatus | None, Query(alias="status")] = None,
    condominium_id: uuid.UUID | None = None,
    debtor_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgreementResponse]:
    filters = AgreementFilters(
        status=agreement_status, condominium_id=condominium_id, debtor_id=debtor_id
    )
    agreements = agreement_service.search(filters, limit, offset)
    return [AgreementResponse.model_validate(agreement) for agreement in agreements]


@router.get("/{agreement_id}")
def get_agreement(
    agreement_id: uuid.UUID, agreement_service: AgreementServiceDependency
) -> AgreementResponse:
    return AgreementResponse.model_validate(agreement_service.get(agreement_id))

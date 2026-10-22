import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from advocondo.acordos.dependencies import (
    get_agreement_service,
    get_lawyer_assignment_service,
)
from advocondo.acordos.lawyer_assignment import LawyerAssignmentService
from advocondo.acordos.models import AgreementStatus
from advocondo.acordos.repository import AgreementFilters
from advocondo.acordos.schemas import (
    AgreementCancelRequest,
    AgreementCreateRequest,
    AgreementResponse,
    LawyerAssignmentRequest,
    LawyerAssignmentResponse,
)
from advocondo.acordos.service import AgreementService
from advocondo.auth.dependencies import CurrentUser, require_office_staff

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

router = APIRouter(
    prefix="/agreements",
    tags=["agreements"],
    dependencies=[Depends(require_office_staff)],
)

AgreementServiceDependency = Annotated[AgreementService, Depends(get_agreement_service)]
LawyerAssignmentServiceDependency = Annotated[
    LawyerAssignmentService, Depends(get_lawyer_assignment_service)
]


@router.post("", status_code=status.HTTP_201_CREATED)
def register_agreement(
    request: AgreementCreateRequest,
    current_user: CurrentUser,
    agreement_service: AgreementServiceDependency,
) -> AgreementResponse:
    agreement = agreement_service.register(request, current_user)
    return AgreementResponse.model_validate(agreement)


@router.get("")
def search_agreements(
    agreement_service: AgreementServiceDependency,
    agreement_status: Annotated[AgreementStatus | None, Query(alias="status")] = None,
    condominium_id: uuid.UUID | None = None,
    debtor_id: uuid.UUID | None = None,
    responsible_lawyer_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgreementResponse]:
    filters = AgreementFilters(
        status=agreement_status,
        condominium_id=condominium_id,
        debtor_id=debtor_id,
        responsible_lawyer_id=responsible_lawyer_id,
    )
    agreements = agreement_service.search(filters, limit, offset)
    return [AgreementResponse.model_validate(agreement) for agreement in agreements]


@router.get("/{agreement_id}")
def get_agreement(
    agreement_id: uuid.UUID, agreement_service: AgreementServiceDependency
) -> AgreementResponse:
    return AgreementResponse.model_validate(agreement_service.get(agreement_id))


@router.post("/{agreement_id}/cancel")
def cancel_agreement(
    agreement_id: uuid.UUID,
    request: AgreementCancelRequest,
    agreement_service: AgreementServiceDependency,
) -> AgreementResponse:
    return AgreementResponse.model_validate(
        agreement_service.cancel(agreement_id, request)
    )


@router.put("/{agreement_id}/responsible-lawyer")
def assign_responsible_lawyer(
    agreement_id: uuid.UUID,
    request: LawyerAssignmentRequest,
    current_user: CurrentUser,
    assignment_service: LawyerAssignmentServiceDependency,
) -> AgreementResponse:
    agreement = assignment_service.assign(agreement_id, request.lawyer_id, current_user)
    return AgreementResponse.model_validate(agreement)


@router.get("/{agreement_id}/lawyer-history")
def list_lawyer_history(
    agreement_id: uuid.UUID, assignment_service: LawyerAssignmentServiceDependency
) -> list[LawyerAssignmentResponse]:
    history = assignment_service.history(agreement_id)
    return [LawyerAssignmentResponse.model_validate(entry) for entry in history]

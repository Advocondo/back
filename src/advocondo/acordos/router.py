from typing import Annotated

from fastapi import APIRouter, Depends, status

from advocondo.acordos.dependencies import get_agreement_service
from advocondo.acordos.schemas import AgreementCreateRequest, AgreementResponse
from advocondo.acordos.service import AgreementService
from advocondo.auth.dependencies import require_office_staff

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

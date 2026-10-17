from typing import Annotated

from fastapi import APIRouter, Depends, status

from advocondo.auth.dependencies import require_office_staff
from advocondo.condominios.dependencies import get_condominium_service
from advocondo.condominios.schemas import CondominiumCreateRequest, CondominiumResponse
from advocondo.condominios.service import CondominiumService

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

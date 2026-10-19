import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from advocondo.auth.dependencies import require_office_staff
from advocondo.common.dependencies import Today
from advocondo.parcelas.dependencies import get_installment_service
from advocondo.parcelas.schemas import InstallmentResponse, InstallmentUpdateRequest
from advocondo.parcelas.service import InstallmentService

router = APIRouter(tags=["installments"], dependencies=[Depends(require_office_staff)])

InstallmentServiceDependency = Annotated[
    InstallmentService, Depends(get_installment_service)
]


@router.get("/agreements/{agreement_id}/installments")
def list_installment_plan(
    agreement_id: uuid.UUID,
    installment_service: InstallmentServiceDependency,
    today: Today,
) -> list[InstallmentResponse]:
    installments = installment_service.list_plan(agreement_id)
    return [InstallmentResponse.from_installment(item, today) for item in installments]


@router.patch("/installments/{installment_id}")
def update_installment(
    installment_id: uuid.UUID,
    request: InstallmentUpdateRequest,
    installment_service: InstallmentServiceDependency,
    today: Today,
) -> list[InstallmentResponse]:
    plan = installment_service.update(installment_id, request)
    return [InstallmentResponse.from_installment(item, today) for item in plan]

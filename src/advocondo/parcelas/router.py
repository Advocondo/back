import uuid
from datetime import MAXYEAR, MINYEAR
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from advocondo.auth.dependencies import require_office_staff
from advocondo.common.dependencies import Today
from advocondo.parcelas.dependencies import get_installment_service
from advocondo.parcelas.repository import InstallmentFilters
from advocondo.parcelas.schemas import (
    InstallmentResponse,
    InstallmentUpdateRequest,
    InstallmentWithDebtorResponse,
    PaymentCorrectionRequest,
    PaymentRequest,
    PaymentResponse,
)
from advocondo.parcelas.service import InstallmentService
from advocondo.parcelas.status import InstallmentStatus
from advocondo.users.dependencies import require_admin

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

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


@router.get("/installments")
def list_installments_due_in_month(
    installment_service: InstallmentServiceDependency,
    today: Today,
    # Anos que as datas do Python não aceitam recebem 422, em vez de erro 500.
    year: Annotated[int | None, Query(ge=MINYEAR, le=MAXYEAR)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    condominium_id: uuid.UUID | None = None,
    responsible_lawyer_id: uuid.UUID | None = None,
    installment_status: Annotated[
        InstallmentStatus | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InstallmentWithDebtorResponse]:
    """Parcelas que vencem no mês; por padrão, o mês atual no Brasil (US25)."""
    filters = InstallmentFilters(
        condominium_id=condominium_id,
        responsible_lawyer_id=responsible_lawyer_id,
        status=installment_status,
    )
    installments = installment_service.list_due_in_month(
        year if year is not None else today.year,
        month if month is not None else today.month,
        filters,
        today,
        limit,
        offset,
    )
    return [
        InstallmentWithDebtorResponse.from_installment(item, today)
        for item in installments
    ]


@router.patch("/installments/{installment_id}")
def update_installment(
    installment_id: uuid.UUID,
    request: InstallmentUpdateRequest,
    installment_service: InstallmentServiceDependency,
    today: Today,
) -> list[InstallmentResponse]:
    plan = installment_service.update(installment_id, request)
    return [InstallmentResponse.from_installment(item, today) for item in plan]


@router.post("/installments/{installment_id}/payment")
def record_payment(
    installment_id: uuid.UUID,
    request: PaymentRequest,
    installment_service: InstallmentServiceDependency,
    today: Today,
) -> InstallmentResponse:
    installment = installment_service.record_payment(
        installment_id, request.payment_date, request.amount, today
    )
    return InstallmentResponse.from_installment(installment, today)


@router.get("/installments/{installment_id}/payments")
def list_payments(
    installment_id: uuid.UUID, installment_service: InstallmentServiceDependency
) -> list[PaymentResponse]:
    payments = installment_service.list_payments(installment_id)
    return [PaymentResponse.model_validate(payment) for payment in payments]


# Corrigir ou estornar uma baixa é restrito ao Administrador (US26-CA02).
@router.put(
    "/installments/{installment_id}/payment", dependencies=[Depends(require_admin)]
)
def correct_payment(
    installment_id: uuid.UUID,
    request: PaymentCorrectionRequest,
    installment_service: InstallmentServiceDependency,
    today: Today,
) -> InstallmentResponse:
    installment = installment_service.correct_payment(
        installment_id, request.payment_date, today
    )
    return InstallmentResponse.from_installment(installment, today)


@router.delete(
    "/installments/{installment_id}/payment", dependencies=[Depends(require_admin)]
)
def reverse_payment(
    installment_id: uuid.UUID,
    installment_service: InstallmentServiceDependency,
    today: Today,
) -> InstallmentResponse:
    installment = installment_service.reverse_payment(installment_id)
    return InstallmentResponse.from_installment(installment, today)

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from advocondo.painel_admin.dependencies import get_admin_panel_service
from advocondo.painel_admin.export import XLSX_MEDIA_TYPE
from advocondo.painel_admin.schemas import AdminDashboardSummary, AdminFinancialSummary
from advocondo.painel_admin.service import AdminPanelService
from advocondo.parcelas.status import InstallmentStatus
from advocondo.users.dependencies import CurrentAdmin

router = APIRouter(prefix="/admin-panel", tags=["admin-panel"])


@router.get("/financial", response_model=AdminFinancialSummary)
def get_financial_summary(
    current_admin: CurrentAdmin,
    service: Annotated[AdminPanelService, Depends(get_admin_panel_service)],
) -> AdminFinancialSummary:
    return service.get_financial_summary(current_admin)


@router.get("/dashboard", response_model=AdminDashboardSummary)
def get_dashboard(
    current_admin: CurrentAdmin,
    service: Annotated[AdminPanelService, Depends(get_admin_panel_service)],
    year: Annotated[int, Query(ge=1, le=9998)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> AdminDashboardSummary:
    return service.get_dashboard(current_admin, year, month)


@router.get("/reports/export")
def export_monthly_followup(
    current_admin: CurrentAdmin,
    service: Annotated[AdminPanelService, Depends(get_admin_panel_service)],
    year: Annotated[int, Query(ge=1, le=9998)],
    month: Annotated[int, Query(ge=1, le=12)],
    condominium_id: uuid.UUID | None = None,
    responsible_lawyer_id: uuid.UUID | None = None,
    status: InstallmentStatus | None = None,
) -> Response:
    content = service.export_monthly_followup(
        current_admin,
        year,
        month,
        condominium_id=condominium_id,
        responsible_lawyer_id=responsible_lawyer_id,
        status=status,
    )
    filename = f"acompanhamento_{year}_{month:02}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from advocondo.auth.dependencies import CurrentClient
from advocondo.common.dependencies import Today
from advocondo.painel_cliente.dependencies import get_client_panel_service
from advocondo.painel_cliente.monthly_report_dependencies import (
    get_monthly_report_service,
)
from advocondo.painel_cliente.monthly_report_service import (
    CondominiumMonthlyReportService,
)
from advocondo.painel_cliente.schemas import AgreementSummary
from advocondo.painel_cliente.service import ClientPanelService

router = APIRouter(prefix="/client-panel", tags=["client-panel"])

ClientPanelServiceDependency = Annotated[
    ClientPanelService, Depends(get_client_panel_service)
]
MonthlyReportServiceDependency = Annotated[
    CondominiumMonthlyReportService, Depends(get_monthly_report_service)
]


@router.get("/agreements")
def list_agreements(
    current_client: CurrentClient,
    panel_service: ClientPanelServiceDependency,
    today: Today,
) -> list[AgreementSummary]:
    return panel_service.list_agreements(current_client.id, today)


@router.get(
    "/condominiums/{condominium_id}/report",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_condominium_report(
    condominium_id: uuid.UUID,
    current_client: CurrentClient,
    panel_service: ClientPanelServiceDependency,
    today: Today,
) -> Response:
    content = panel_service.condominium_report(
        current_client.id, condominium_id, current_client.name, today
    )
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="relatorio-condominio.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/condominiums/{condominium_id}/reports/{year}/{month}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_monthly_condominium_report(
    condominium_id: uuid.UUID,
    year: Annotated[int, Path(ge=1, le=9998)],
    month: Annotated[int, Path(ge=1, le=12)],
    current_client: CurrentClient,
    report_service: MonthlyReportServiceDependency,
) -> Response:
    report, content = report_service.download_for_client(
        current_client.id, condominium_id, year, month
    )
    return Response(
        content,
        media_type=report.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{report.file_name}"',
            "Cache-Control": "no-store",
        },
    )

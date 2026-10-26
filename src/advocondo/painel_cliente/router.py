import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from advocondo.auth.dependencies import CurrentClient
from advocondo.common.dependencies import Today
from advocondo.painel_cliente.dependencies import get_client_panel_service
from advocondo.painel_cliente.schemas import (
    AgreementSummary,
    ClientInstallment,
    DebtorPaymentHistory,
)
from advocondo.painel_cliente.service import ClientPanelService

router = APIRouter(prefix="/client-panel", tags=["client-panel"])

ClientPanelServiceDependency = Annotated[
    ClientPanelService, Depends(get_client_panel_service)
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


@router.get("/agreements/{agreement_id}/installments")
def list_unpaid_installments(
    agreement_id: uuid.UUID,
    current_client: CurrentClient,
    panel_service: ClientPanelServiceDependency,
    today: Today,
) -> list[ClientInstallment]:
    return panel_service.list_unpaid_installments(
        current_client.id, agreement_id, today
    )


@router.get("/debtors/{debtor_id}/history")
def get_debtor_history(
    debtor_id: uuid.UUID,
    current_client: CurrentClient,
    panel_service: ClientPanelServiceDependency,
    today: Today,
) -> DebtorPaymentHistory:
    return panel_service.debtor_history(current_client.id, debtor_id, today)

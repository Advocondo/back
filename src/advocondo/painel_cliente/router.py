from typing import Annotated

from fastapi import APIRouter, Depends

from advocondo.auth.dependencies import CurrentClient
from advocondo.common.dependencies import Today
from advocondo.painel_cliente.dependencies import get_client_panel_service
from advocondo.painel_cliente.schemas import AgreementSummary
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

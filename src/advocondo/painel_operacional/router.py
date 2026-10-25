from typing import Annotated

from fastapi import APIRouter, Depends

from advocondo.auth.dependencies import CurrentOperator
from advocondo.painel_operacional.dependencies import get_operational_panel_service
from advocondo.painel_operacional.schemas import OperationalFinancialSummary
from advocondo.painel_operacional.service import OperationalPanelService

router = APIRouter(prefix="/operator-panel", tags=["operator-panel"])


@router.get("/financial", response_model=OperationalFinancialSummary)
def get_financial_summary(
    current_operator: CurrentOperator,
    service: Annotated[OperationalPanelService, Depends(get_operational_panel_service)],
) -> OperationalFinancialSummary:
    return service.get_financial_summary(current_operator)

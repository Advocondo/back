from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.common.clock import Clock, get_clock
from advocondo.db import get_session
from advocondo.metas.repository import GoalRepository
from advocondo.painel_operacional.repository import OperationalPanelRepository
from advocondo.painel_operacional.service import OperationalPanelService


def get_operational_panel_service(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> OperationalPanelService:
    return OperationalPanelService(
        OperationalPanelRepository(session), GoalRepository(session), clock
    )

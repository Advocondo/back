from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.common.clock import Clock, get_clock
from advocondo.db import get_session
from advocondo.painel_admin.repository import AdminPanelRepository
from advocondo.painel_admin.service import AdminPanelService


def get_admin_panel_service(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AdminPanelService:
    return AdminPanelService(AdminPanelRepository(session), clock)

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.db import get_session
from advocondo.painel_cliente.repository import ClientPanelRepository
from advocondo.painel_cliente.service import ClientPanelService


def get_client_panel_service(
    session: Annotated[Session, Depends(get_session)],
) -> ClientPanelService:
    return ClientPanelService(ClientPanelRepository(session))

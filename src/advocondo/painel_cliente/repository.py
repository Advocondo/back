import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.users.models import UserCondominium


def client_agreements_query(user_id: uuid.UUID) -> Select[Agreement]:
    """Active agreements of the condominiums linked to the user (US37-CA01).

    The link is a JOIN, so agreements of other condominiums never leave the database,
    and a Client with no link gets no row (US10-CA02).
    """
    return (
        select(Agreement)
        .join(
            UserCondominium,
            UserCondominium.condominium_id == Agreement.condominium_id,
        )
        .where(
            UserCondominium.user_id == user_id,
            Agreement.status == AgreementStatus.ACTIVE,
        )
        .options(selectinload(Agreement.installments))
    )


class ClientPanelRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_agreements_of_client(self, user_id: uuid.UUID) -> Sequence[Agreement]:
        return self._session.scalars(client_agreements_query(user_id)).all()

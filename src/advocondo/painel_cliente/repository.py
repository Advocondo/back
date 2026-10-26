import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.users.models import UserCondominium


def client_agreements_query(user_id: uuid.UUID) -> Select[Agreement]:
    """Active agreements of the condominiums linked to the user (US37-CA01), ordered
    by condominium and debtor name like the other listings.

    The link is a JOIN, so agreements of other condominiums never leave the database,
    and a Client with no link gets no row (US10-CA02).
    """
    return (
        select(Agreement)
        .join(
            UserCondominium,
            UserCondominium.condominium_id == Agreement.condominium_id,
        )
        .join(Condominium, Condominium.id == Agreement.condominium_id)
        .join(Debtor, Debtor.id == Agreement.debtor_id)
        .where(
            UserCondominium.user_id == user_id,
            Agreement.status == AgreementStatus.ACTIVE,
        )
        .order_by(Condominium.name, Debtor.name, Agreement.id)
        .options(selectinload(Agreement.installments))
    )


class ClientPanelRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_agreements_of_client(self, user_id: uuid.UUID) -> Sequence[Agreement]:
        return self._session.scalars(client_agreements_query(user_id)).all()

    def get_linked_condominium(
        self, user_id: uuid.UUID, condominium_id: uuid.UUID
    ) -> Condominium | None:
        """Resolve a condominium only through the requesting Client's link."""
        query = (
            select(Condominium)
            .join(
                UserCondominium,
                UserCondominium.condominium_id == Condominium.id,
            )
            .where(
                UserCondominium.user_id == user_id,
                Condominium.id == condominium_id,
            )
        )
        return self._session.scalar(query)

    def list_active_agreements_for_condominium(
        self, user_id: uuid.UUID, condominium_id: uuid.UUID
    ) -> Sequence[Agreement]:
        """Active agreements constrained to both the Client link and condominium."""

        query = (
            select(Agreement)
            .join(
                UserCondominium,
                UserCondominium.condominium_id == Agreement.condominium_id,
            )
            .where(
                UserCondominium.user_id == user_id,
                Agreement.condominium_id == condominium_id,
                Agreement.status == AgreementStatus.ACTIVE,
            )
            .order_by(Agreement.id)
            .options(selectinload(Agreement.installments))
        )
        return self._session.scalars(query).all()

    def get_agreement_of_client(
        self, user_id: uuid.UUID, agreement_id: uuid.UUID
    ) -> Agreement | None:
        """The agreement, only if the Client could see it in the panel."""
        query = client_agreements_query(user_id).where(Agreement.id == agreement_id)
        return self._session.scalars(query).one_or_none()

    def get_debtor_of_client(
        self, user_id: uuid.UUID, debtor_id: uuid.UUID
    ) -> Debtor | None:
        """The debtor, only if they belong to a condominium linked to the Client."""
        query = (
            select(Debtor)
            .join(
                UserCondominium,
                UserCondominium.condominium_id == Debtor.condominium_id,
            )
            .where(UserCondominium.user_id == user_id, Debtor.id == debtor_id)
        )
        return self._session.scalars(query).one_or_none()

    def list_agreements_of_debtor(
        self, user_id: uuid.UUID, debtor_id: uuid.UUID
    ) -> Sequence[Agreement]:
        """Every agreement of the debtor, cancelled ones included (US38): the
        history keeps what was paid on them. Still limited to linked condominiums."""
        query = (
            select(Agreement)
            .join(
                UserCondominium,
                UserCondominium.condominium_id == Agreement.condominium_id,
            )
            .where(
                UserCondominium.user_id == user_id,
                Agreement.debtor_id == debtor_id,
            )
            .options(selectinload(Agreement.installments))
        )
        return self._session.scalars(query).all()

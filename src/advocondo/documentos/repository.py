import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement
from advocondo.documentos.models import AgreementPdf
from advocondo.painel_cliente.repository import client_agreements_query


class AgreementPdfRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, agreement_id: uuid.UUID, pdf_id: uuid.UUID) -> AgreementPdf | None:
        """O PDF só é achado pelo acordo dele, para a permissão do acordo valer."""
        return self._session.scalar(
            select(AgreementPdf).where(
                AgreementPdf.id == pdf_id, AgreementPdf.agreement_id == agreement_id
            )
        )

    def list_by_agreement(self, agreement_id: uuid.UUID) -> Sequence[AgreementPdf]:
        """Do mais recente para o mais antigo, sem carregar os bytes."""
        return self._session.scalars(
            select(AgreementPdf)
            .where(AgreementPdf.agreement_id == agreement_id)
            .order_by(AgreementPdf.generated_at.desc(), AgreementPdf.id)
        ).all()

    def client_sees_agreement(
        self, user_id: uuid.UUID, agreement_id: uuid.UUID
    ) -> bool:
        """Mesma regra do painel do Cliente (US37): acordo ativo de um condomínio
        vinculado a ele (US10)."""
        query = client_agreements_query(user_id).where(Agreement.id == agreement_id)
        return self._session.scalar(query.limit(1)) is not None

    def save(self, pdf: AgreementPdf) -> None:
        self._session.add(pdf)
        self._session.flush()

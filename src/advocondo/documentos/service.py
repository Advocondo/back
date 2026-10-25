import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from advocondo.acordos.errors import AgreementNotFoundError
from advocondo.acordos.models import Agreement
from advocondo.acordos.repository import AgreementRepository
from advocondo.common.clock import Clock, today_in_brazil
from advocondo.common.pdf import PDF_CONTENT_TYPE
from advocondo.common.storage import FileStorage
from advocondo.documentos.agreement_pdf import render_agreement_pdf
from advocondo.documentos.errors import AgreementPdfNotFoundError
from advocondo.documentos.models import AgreementPdf
from advocondo.documentos.repository import AgreementPdfRepository
from advocondo.users.models import Role, User


class AgreementPdfService:
    def __init__(
        self,
        session: Session,
        pdfs: AgreementPdfRepository,
        agreements: AgreementRepository,
        storage: FileStorage,
        clock: Clock,
    ) -> None:
        self._session = session
        self._pdfs = pdfs
        self._agreements = agreements
        self._storage = storage
        self._clock = clock

    def generate(self, agreement_id: uuid.UUID, generated_by: User) -> AgreementPdf:
        """Gera o PDF com os dados atuais do acordo e o guarda (US24-CA01)."""
        agreement = self._agreements.get(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()

        now = self._clock.now()
        content = render_agreement_pdf(agreement, now, today_in_brazil(now))
        pdf = AgreementPdf(
            # O id é escolhido aqui porque entra na chave do arquivo no bucket.
            id=uuid.uuid4(),
            agreement_id=agreement.id,
            generated_by=generated_by,
            generated_at=now,
        )
        key = f"agreements/{agreement.id}/pdfs/{pdf.id}.pdf"
        self._storage.save(pdf, key, content, PDF_CONTENT_TYPE)
        self._pdfs.save(pdf)
        self._session.commit()
        return pdf

    def list(self, agreement_id: uuid.UUID, user: User) -> Sequence[AgreementPdf]:
        self._visible_agreement(agreement_id, user)
        return self._pdfs.list_by_agreement(agreement_id)

    def download(
        self, agreement_id: uuid.UUID, pdf_id: uuid.UUID, user: User
    ) -> tuple[AgreementPdf, bytes]:
        """O link de acesso segue a permissão do acordo (US24-CA02, CA03)."""
        self._visible_agreement(agreement_id, user)
        pdf = self._pdfs.get(agreement_id, pdf_id)
        if pdf is None:
            raise AgreementPdfNotFoundError()
        return pdf, self._storage.load(pdf)

    def _visible_agreement(self, agreement_id: uuid.UUID, user: User) -> Agreement:
        """O escritório vê todos os acordos. O Cliente só vê os do painel dele; os
        outros respondem como inexistentes, para não revelar que existem."""
        agreement = self._agreements.get(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()
        if user.role == Role.CLIENT and not self._pdfs.client_sees_agreement(
            user.id, agreement_id
        ):
            raise AgreementNotFoundError()
        return agreement

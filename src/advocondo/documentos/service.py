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
from advocondo.documentos.errors import (
    AgreementPdfNotFoundError,
    DocumentIsALinkError,
    DocumentNotFoundError,
    FileOrLinkRequiredError,
)
from advocondo.documentos.models import AgreementDocument, AgreementPdf, DocumentKind
from advocondo.documentos.repository import AgreementPdfRepository, DocumentRepository
from advocondo.documentos.rules import (
    clean_filename,
    filename_for_link,
    validate_document,
    validate_url,
)
from advocondo.users.models import Role, User


class DocumentService:
    def __init__(
        self,
        session: Session,
        agreements: AgreementRepository,
        documents: DocumentRepository,
        clock: Clock,
    ) -> None:
        self._session = session
        self._agreements = agreements
        self._documents = documents
        self._clock = clock

    def attach(
        self,
        agreement_id: uuid.UUID,
        attached_by: User,
        content: bytes | None,
        filename: str | None,
        url: str | None,
        name: str | None,
    ) -> AgreementDocument:
        """Anexa ao acordo um arquivo guardado aqui ou um link (US21)."""
        self._ensure_agreement_exists(agreement_id)
        if content is not None and url is None:
            document = file_document(filename, content)
        elif url is not None and content is None:
            document = link_document(url, name)
        else:
            raise FileOrLinkRequiredError()

        document.agreement_id = agreement_id
        document.uploaded_by = attached_by
        document.uploaded_at = self._clock.now()
        self._documents.save(document)
        self._session.commit()
        return document

    def get_file(
        self, agreement_id: uuid.UUID, document_id: uuid.UUID
    ) -> AgreementDocument:
        """Documento do tipo arquivo, pronto para baixar. Link não se baixa."""
        self._ensure_agreement_exists(agreement_id)
        document = self._documents.get(agreement_id, document_id)
        if document is None:
            raise DocumentNotFoundError()
        if document.kind is DocumentKind.LINK:
            raise DocumentIsALinkError()
        return document

    def list_by_agreement(self, agreement_id: uuid.UUID) -> Sequence[AgreementDocument]:
        self._ensure_agreement_exists(agreement_id)
        return self._documents.list_by_agreement(agreement_id)

    def _ensure_agreement_exists(self, agreement_id: uuid.UUID) -> None:
        if self._agreements.get(agreement_id) is None:
            raise AgreementNotFoundError()


def file_document(filename: str | None, content: bytes) -> AgreementDocument:
    return AgreementDocument(
        filename=clean_filename(filename),
        content_type=validate_document(content),
        size=len(content),
        content=content,
    )


def link_document(url: str, name: str | None) -> AgreementDocument:
    clean_url = validate_url(url)
    return AgreementDocument(filename=filename_for_link(clean_url, name), url=clean_url)


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

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.acordos.repository import AgreementRepository
from advocondo.common.clock import Clock, get_clock
from advocondo.common.storage import FileStorage, get_file_storage
from advocondo.db import get_session
from advocondo.documentos.repository import AgreementPdfRepository, DocumentRepository
from advocondo.documentos.service import AgreementPdfService, DocumentService


def get_document_service(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> DocumentService:
    return DocumentService(
        session, AgreementRepository(session), DocumentRepository(session), clock
    )


def get_agreement_pdf_service(
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AgreementPdfService:
    return AgreementPdfService(
        session=session,
        pdfs=AgreementPdfRepository(session),
        agreements=AgreementRepository(session),
        storage=storage,
        clock=clock,
    )

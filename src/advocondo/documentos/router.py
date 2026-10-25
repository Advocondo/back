import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from advocondo.auth.dependencies import CurrentUser, require_office_staff
from advocondo.documentos.dependencies import (
    get_agreement_pdf_service,
    get_document_service,
)
from advocondo.documentos.rules import MAX_DOCUMENT_SIZE
from advocondo.documentos.schemas import AgreementPdfResponse, DocumentResponse
from advocondo.documentos.service import AgreementPdfService, DocumentService

router = APIRouter()

AgreementPdfServiceDependency = Annotated[
    AgreementPdfService, Depends(get_agreement_pdf_service)
]
DocumentServiceDependency = Annotated[DocumentService, Depends(get_document_service)]


@router.post(
    "/agreements/{agreement_id}/documents",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_office_staff)],
    tags=["documents"],
)
def upload_document(
    agreement_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    current_user: CurrentUser,
    document_service: DocumentServiceDependency,
) -> DocumentResponse:
    # Lê um byte a mais que o limite, só para saber que passou dele.
    content = file.file.read(MAX_DOCUMENT_SIZE + 1)
    document = document_service.upload(
        agreement_id, file.filename, content, current_user
    )
    return DocumentResponse.model_validate(document)


@router.get(
    "/agreements/{agreement_id}/documents",
    dependencies=[Depends(require_office_staff)],
    tags=["documents"],
)
def list_documents(
    agreement_id: uuid.UUID, document_service: DocumentServiceDependency
) -> list[DocumentResponse]:
    documents = document_service.list_by_agreement(agreement_id)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get(
    "/agreements/{agreement_id}/documents/{document_id}",
    dependencies=[Depends(require_office_staff)],
    tags=["documents"],
)
def download_document(
    agreement_id: uuid.UUID,
    document_id: uuid.UUID,
    document_service: DocumentServiceDependency,
) -> Response:
    document = document_service.get(agreement_id, document_id)
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


# Gerar é da Equipe Operacional e do Administrador (US24).
@router.post(
    "/agreements/{agreement_id}/pdfs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_office_staff)],
    tags=["agreement-pdfs"],
)
def generate_agreement_pdf(
    agreement_id: uuid.UUID,
    current_user: CurrentUser,
    pdf_service: AgreementPdfServiceDependency,
) -> AgreementPdfResponse:
    pdf = pdf_service.generate(agreement_id, current_user)
    return AgreementPdfResponse.from_pdf(pdf)


# Sem dependência de perfil no router: o Cliente lista e baixa os PDFs dos acordos
# que ele vê (US24-CA03); o service aplica a regra.
@router.get("/agreements/{agreement_id}/pdfs", tags=["agreement-pdfs"])
def list_agreement_pdfs(
    agreement_id: uuid.UUID,
    current_user: CurrentUser,
    pdf_service: AgreementPdfServiceDependency,
) -> list[AgreementPdfResponse]:
    pdfs = pdf_service.list(agreement_id, current_user)
    return [AgreementPdfResponse.from_pdf(pdf) for pdf in pdfs]


@router.get(
    "/agreements/{agreement_id}/pdfs/{pdf_id}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    tags=["agreement-pdfs"],
)
def download_agreement_pdf(
    agreement_id: uuid.UUID,
    pdf_id: uuid.UUID,
    current_user: CurrentUser,
    pdf_service: AgreementPdfServiceDependency,
) -> Response:
    pdf, content = pdf_service.download(agreement_id, pdf_id, current_user)
    return Response(
        content,
        media_type=pdf.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{pdf.file_name}"',
            # Documento com dados pessoais: nenhum cache guarda uma cópia.
            "Cache-Control": "no-store",
        },
    )

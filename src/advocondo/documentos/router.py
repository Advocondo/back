import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Response, UploadFile, status

from advocondo.auth.dependencies import CurrentUser, require_office_staff
from advocondo.documentos.dependencies import (
    get_agreement_pdf_service,
    get_document_service,
)
from advocondo.documentos.rules import MAX_DOCUMENT_SIZE
from advocondo.documentos.schemas import AgreementPdfResponse, DocumentResponse
from advocondo.documentos.service import AgreementPdfService, DocumentService

router = APIRouter()
document_router = APIRouter(
    prefix="/agreements",
    tags=["documents"],
    dependencies=[Depends(require_office_staff)],
)

AgreementPdfServiceDependency = Annotated[
    AgreementPdfService, Depends(get_agreement_pdf_service)
]
DocumentServiceDependency = Annotated[DocumentService, Depends(get_document_service)]


@document_router.post("/{agreement_id}/documents", status_code=status.HTTP_201_CREATED)
def upload_document(
    agreement_id: uuid.UUID,
    current_user: CurrentUser,
    document_service: DocumentServiceDependency,
    file: UploadFile | None = None,
    url: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
) -> DocumentResponse:
    # Lê um byte a mais que o limite, só para saber que passou dele.
    content = file.file.read(MAX_DOCUMENT_SIZE + 1) if file is not None else None
    document = document_service.attach(
        agreement_id,
        current_user,
        content=content,
        filename=file.filename if file is not None else None,
        url=url,
        name=name,
    )
    return DocumentResponse.model_validate(document)


@document_router.get("/{agreement_id}/documents")
def list_documents(
    agreement_id: uuid.UUID, document_service: DocumentServiceDependency
) -> list[DocumentResponse]:
    documents = document_service.list_by_agreement(agreement_id)
    return [DocumentResponse.model_validate(document) for document in documents]


@document_router.get("/{agreement_id}/documents/{document_id}")
def download_document(
    agreement_id: uuid.UUID,
    document_id: uuid.UUID,
    document_service: DocumentServiceDependency,
) -> Response:
    document, file, content = document_service.download(agreement_id, document_id)
    return Response(
        content=content,
        media_type=file.content_type,
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


router.include_router(document_router)

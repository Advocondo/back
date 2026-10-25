import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from advocondo.auth.dependencies import CurrentUser, require_office_staff
from advocondo.documentos.dependencies import get_agreement_pdf_service
from advocondo.documentos.schemas import AgreementPdfResponse
from advocondo.documentos.service import AgreementPdfService

# Sem dependência de perfil no router: o Cliente lista e baixa os PDFs dos acordos
# que ele vê (US24-CA03); o service aplica a regra.
router = APIRouter(prefix="/agreements/{agreement_id}/pdfs", tags=["agreement-pdfs"])

AgreementPdfServiceDependency = Annotated[
    AgreementPdfService, Depends(get_agreement_pdf_service)
]


# Gerar é da Equipe Operacional e do Administrador (US24).
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_office_staff)],
)
def generate_agreement_pdf(
    agreement_id: uuid.UUID,
    current_user: CurrentUser,
    pdf_service: AgreementPdfServiceDependency,
) -> AgreementPdfResponse:
    pdf = pdf_service.generate(agreement_id, current_user)
    return AgreementPdfResponse.from_pdf(pdf)


@router.get("")
def list_agreement_pdfs(
    agreement_id: uuid.UUID,
    current_user: CurrentUser,
    pdf_service: AgreementPdfServiceDependency,
) -> list[AgreementPdfResponse]:
    pdfs = pdf_service.list(agreement_id, current_user)
    return [AgreementPdfResponse.from_pdf(pdf) for pdf in pdfs]


@router.get(
    "/{pdf_id}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
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

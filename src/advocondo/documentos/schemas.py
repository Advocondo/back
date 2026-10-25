import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from advocondo.acordos.schemas import UserSummary
from advocondo.documentos.models import AgreementPdf, DocumentKind
from advocondo.users.schemas import ActorResponse


def download_path(agreement_id: uuid.UUID, pdf_id: uuid.UUID) -> str:
    return f"/agreements/{agreement_id}/pdfs/{pdf_id}"


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: DocumentKind
    filename: str
    # Tipo e tamanho só existem para arquivos; o endereço, só para links.
    content_type: str | None
    size: int | None
    url: str | None
    uploaded_at: datetime
    uploaded_by: ActorResponse


class AgreementPdfResponse(BaseModel):
    id: uuid.UUID
    agreement_id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    generated_by: UserSummary
    generated_at: datetime
    # Link de acesso (US24-CA02): rota da API, que exige login e aplica a
    # permissão do acordo a cada download.
    download_url: str

    @classmethod
    def from_pdf(cls, pdf: AgreementPdf) -> "AgreementPdfResponse":
        return cls(
            id=pdf.id,
            agreement_id=pdf.agreement_id,
            file_name=pdf.file_name,
            content_type=pdf.content_type,
            size_bytes=pdf.size_bytes,
            generated_by=UserSummary.model_validate(pdf.generated_by),
            generated_at=pdf.generated_at,
            download_url=download_path(pdf.agreement_id, pdf.id),
        )

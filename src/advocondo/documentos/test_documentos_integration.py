from collections.abc import Iterator
from datetime import date, timedelta
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement
from advocondo.common.storage import ObjectStorage, get_file_storage
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.documentos.models import AgreementDocument, AgreementPdf
from advocondo.main import app
from advocondo.users.models import Role, User
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.devedores import CreateDebtor
from tests.fixtures.painel_cliente import CreateAgreementWithInstallments, LinkClient
from tests.fixtures.users import CreateUser
from tests.support.clock import FrozenClock
from tests.support.pdf import pdf_text
from tests.support.storage import FakeS3Client

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
BUCKET = "advocondo-arquivos"

# Each installment of the fixture is R$ 100,00, of which R$ 10,00 is the office's
# fee and R$ 90,00 goes to the condominium; the agreement's fee is R$ 30,00.
FEE_VALUES = ("R$ 10,00", "R$ 90,00", "R$ 30,00")


def pdfs_url(agreement: Agreement) -> str:
    return f"/agreements/{agreement.id}/pdfs"


def generate(
    client: TestClient, headers: dict[str, str], agreement: Agreement
) -> httpx.Response:
    response: httpx.Response = client.post(pdfs_url(agreement), headers=headers)
    return response


@pytest.fixture
def operator(create_user: CreateUser) -> User:
    return create_user(role=Role.OPERATOR, name="Ana Souza")


@pytest.fixture
def operator_headers(operator: User, authenticate_as: AuthenticateAs) -> dict[str, str]:
    return authenticate_as(operator)


@pytest.fixture
def client_user(create_user: CreateUser) -> User:
    return create_user(role=Role.CLIENT, email="sindico@example.com")


@pytest.fixture
def client_headers(
    client_user: User, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(client_user)


@pytest.fixture
def mirante(create_condominium: CreateCondominium) -> Condominium:
    return create_condominium(name="Residencial Mirante", cnpj="11222333000181")


@pytest.fixture
def jose(mirante: Condominium, create_debtor: CreateDebtor) -> Debtor:
    return create_debtor(mirante, name="José Simão", unit="Bloco B 304")


@pytest.fixture
def agreement(
    mirante: Condominium,
    jose: Debtor,
    create_agreement_with_installments: CreateAgreementWithInstallments,
) -> Agreement:
    """Today is 2026-03-02: one installment paid, one overdue and one open."""
    return create_agreement_with_installments(
        mirante,
        jose,
        [
            (date(2026, 1, 10), date(2026, 1, 9)),
            (date(2026, 2, 10), None),
            (date(2026, 4, 10), None),
        ],
    )


@pytest.fixture
def generated_pdf(
    db_client: TestClient, operator_headers: dict[str, str], agreement: Agreement
) -> dict[str, str]:
    response = generate(db_client, operator_headers, agreement)
    assert response.status_code == 201
    body: dict[str, str] = response.json()
    return body


class TestGenerateAgreementPdf:
    def test_pdf_is_saved_with_its_metadata(
        self,
        db_client: TestClient,
        db_session: Session,
        clock: FrozenClock,
        operator: User,
        operator_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        """US24-CA01"""
        response = generate(db_client, operator_headers, agreement)

        assert response.status_code == 201
        body = response.json()
        assert body["agreement_id"] == str(agreement.id)
        assert body["content_type"] == "application/pdf"
        assert body["generated_by"] == {"id": str(operator.id), "name": "Ana Souza"}
        assert body["generated_at"] == "2026-03-02T09:00:00Z"
        # 09:00 UTC is 06:00 in Brasília.
        assert body["file_name"] == "acordo-20260302-060000.pdf"
        assert body["download_url"] == f"{pdfs_url(agreement)}/{body['id']}"
        saved = db_session.scalars(select(AgreementPdf)).one()
        assert saved.content is not None
        assert saved.content.startswith(b"%PDF")
        assert saved.size_bytes == body["size_bytes"] == len(saved.content)
        assert saved.storage_key is None

    def test_pdf_has_the_main_data_of_the_agreement(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        generated_pdf: dict[str, str],
    ) -> None:
        """US24-CA01"""
        content = db_client.get(
            generated_pdf["download_url"], headers=operator_headers
        ).content

        text = pdf_text(content)
        for expected in (
            "Gerado em 02/03/2026 às 06:00 (horário de Brasília)",
            "Residencial Mirante",
            "11.222.333/0001-81",
            "José Simão",
            "Bloco B 304",
            "Ativo",
            "R$ 300,00",
            "R$ 100,00",
            "R$ 200,00",
            "Não atribuído",
            "10/01/2026",
            "09/01/2026",
            "Pago",
            "Atrasado",
            "Em aberto",
        ):
            assert expected in text

    def test_pdf_never_shows_the_office_fee(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        generated_pdf: dict[str, str],
    ) -> None:
        """The same file goes to the Client (US24-CA03), who never sees fees (US16)."""
        content = db_client.get(
            generated_pdf["download_url"], headers=operator_headers
        ).content

        text = pdf_text(content)
        assert "Honorários" not in text
        assert "10%" not in text
        for fee_value in FEE_VALUES:
            assert fee_value not in text

    def test_admin_also_generates(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        agreement: Agreement,
    ) -> None:
        admin = create_user(role=Role.ADMIN, email="admin@example.com")

        response = generate(db_client, authenticate_as(admin), agreement)

        assert response.status_code == 201

    def test_each_generation_saves_a_new_pdf(
        self,
        db_client: TestClient,
        clock: FrozenClock,
        operator_headers: dict[str, str],
        agreement: Agreement,
        generated_pdf: dict[str, str],
    ) -> None:
        second = generate(db_client, operator_headers, agreement).json()

        assert second["id"] != generated_pdf["id"]

    def test_client_cannot_generate(
        self,
        db_client: TestClient,
        client_user: User,
        client_headers: dict[str, str],
        link_client: LinkClient,
        mirante: Condominium,
        agreement: Agreement,
    ) -> None:
        link_client(client_user, mirante)

        response = generate(db_client, client_headers, agreement)

        assert response.status_code == 403

    def test_unknown_agreement(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.post(
            f"/agreements/{UNKNOWN_ID}/pdfs", headers=operator_headers
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Acordo não encontrado."}

    def test_requires_login(self, db_client: TestClient, agreement: Agreement) -> None:
        assert db_client.post(pdfs_url(agreement)).status_code == 401


class TestListAgreementPdfs:
    def test_office_lists_newest_first(
        self,
        db_client: TestClient,
        clock: FrozenClock,
        operator_headers: dict[str, str],
        agreement: Agreement,
        generated_pdf: dict[str, str],
    ) -> None:
        clock.advance(timedelta(hours=1))
        newest = generate(db_client, operator_headers, agreement).json()

        response = db_client.get(pdfs_url(agreement), headers=operator_headers)

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [
            newest["id"],
            generated_pdf["id"],
        ]

    def test_agreement_without_pdfs(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        response = db_client.get(pdfs_url(agreement), headers=operator_headers)

        assert response.json() == []

    def test_client_lists_pdfs_of_linked_condominium(
        self,
        db_client: TestClient,
        client_user: User,
        client_headers: dict[str, str],
        link_client: LinkClient,
        mirante: Condominium,
        agreement: Agreement,
        generated_pdf: dict[str, str],
    ) -> None:
        """US24-CA03"""
        link_client(client_user, mirante)

        response = db_client.get(pdfs_url(agreement), headers=client_headers)

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [generated_pdf["id"]]

    def test_client_of_another_condominium_does_not_see_the_agreement(
        self,
        db_client: TestClient,
        client_user: User,
        client_headers: dict[str, str],
        link_client: LinkClient,
        create_condominium: CreateCondominium,
        agreement: Agreement,
        generated_pdf: dict[str, str],
    ) -> None:
        """US24-CA03 and US10"""
        link_client(client_user, create_condominium(name="Edifício Aurora"))

        response = db_client.get(pdfs_url(agreement), headers=client_headers)

        assert response.status_code == 404
        assert response.json() == {"detail": "Acordo não encontrado."}

    def test_unknown_agreement(
        self, db_client: TestClient, operator_headers: dict[str, str]
    ) -> None:
        response = db_client.get(
            f"/agreements/{UNKNOWN_ID}/pdfs", headers=operator_headers
        )

        assert response.status_code == 404


class TestDownloadAgreementPdf:
    def test_office_downloads_the_file(
        self,
        db_client: TestClient,
        db_session: Session,
        operator_headers: dict[str, str],
        generated_pdf: dict[str, str],
    ) -> None:
        """US24-CA02"""
        response = db_client.get(
            generated_pdf["download_url"], headers=operator_headers
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"] == (
            'attachment; filename="acordo-20260302-060000.pdf"'
        )
        assert response.headers["cache-control"] == "no-store"
        saved = db_session.scalars(select(AgreementPdf)).one()
        assert response.content == saved.content

    def test_client_downloads_pdf_of_linked_condominium(
        self,
        db_client: TestClient,
        client_user: User,
        client_headers: dict[str, str],
        link_client: LinkClient,
        mirante: Condominium,
        generated_pdf: dict[str, str],
    ) -> None:
        """US24-CA03"""
        link_client(client_user, mirante)

        response = db_client.get(generated_pdf["download_url"], headers=client_headers)

        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")

    def test_client_without_link_gets_not_found(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        generated_pdf: dict[str, str],
    ) -> None:
        """US24-CA03 and US10-CA02"""
        response = db_client.get(generated_pdf["download_url"], headers=client_headers)

        assert response.status_code == 404
        assert response.json() == {"detail": "Acordo não encontrado."}

    def test_pdf_is_found_only_through_its_own_agreement(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        mirante: Condominium,
        jose: Debtor,
        create_agreement_with_installments: CreateAgreementWithInstallments,
        generated_pdf: dict[str, str],
    ) -> None:
        """A Client could otherwise reach a PDF of another condominium through an
        agreement they do see."""
        other = create_agreement_with_installments(mirante, jose, [])

        response = db_client.get(
            f"{pdfs_url(other)}/{generated_pdf['id']}", headers=operator_headers
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "PDF não encontrado."}

    def test_unknown_pdf(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        response = db_client.get(
            f"{pdfs_url(agreement)}/{UNKNOWN_ID}", headers=operator_headers
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "PDF não encontrado."}

    def test_requires_login(
        self, db_client: TestClient, generated_pdf: dict[str, str]
    ) -> None:
        assert db_client.get(generated_pdf["download_url"]).status_code == 401


class TestAgreementPdfInBucket:
    @pytest.fixture
    def s3_client(self) -> Iterator[FakeS3Client]:
        fake = FakeS3Client()
        storage = ObjectStorage(cast("S3Client", fake), BUCKET)
        app.dependency_overrides[get_file_storage] = lambda: storage
        try:
            yield fake
        finally:
            app.dependency_overrides.pop(get_file_storage, None)

    def test_bytes_go_to_the_bucket_and_the_row_keeps_the_key(
        self,
        db_client: TestClient,
        db_session: Session,
        s3_client: FakeS3Client,
        operator_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        body = generate(db_client, operator_headers, agreement).json()

        saved = db_session.scalars(select(AgreementPdf)).one()
        key = f"agreements/{agreement.id}/pdfs/{body['id']}.pdf"
        assert saved.storage_key == key
        assert saved.content is None
        assert s3_client.objects[BUCKET, key].startswith(b"%PDF")
        assert s3_client.content_types[BUCKET, key] == "application/pdf"
        assert saved.size_bytes == len(s3_client.objects[BUCKET, key])

    def test_download_is_served_by_the_api(
        self,
        db_client: TestClient,
        s3_client: FakeS3Client,
        operator_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        body = generate(db_client, operator_headers, agreement).json()

        response = db_client.get(body["download_url"], headers=operator_headers)

        key = f"agreements/{agreement.id}/pdfs/{body['id']}.pdf"
        assert response.status_code == 200
        assert response.content == s3_client.objects[BUCKET, key]


class TestAgreementDocuments:
    def test_upload_list_and_download(
        self,
        db_client: TestClient,
        db_session: Session,
        operator: User,
        operator_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        content = b"%PDF-1.7\nexample agreement"
        response = db_client.post(
            f"/agreements/{agreement.id}/documents",
            headers=operator_headers,
            files={"file": ("../termo.pdf", content, "text/plain")},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["filename"] == "termo.pdf"
        assert body["content_type"] == "application/pdf"
        assert body["size"] == len(content)
        assert body["uploaded_by"] == {"id": str(operator.id), "name": operator.name}
        saved = db_session.scalars(select(AgreementDocument)).one()
        assert saved.content == content

        listed = db_client.get(
            f"/agreements/{agreement.id}/documents", headers=operator_headers
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [body["id"]]

        downloaded = db_client.get(
            f"/agreements/{agreement.id}/documents/{body['id']}",
            headers=operator_headers,
        )
        assert downloaded.status_code == 200
        assert downloaded.content == content
        assert downloaded.headers["content-type"] == "application/pdf"
        assert downloaded.headers["content-disposition"] == (
            "attachment; filename*=UTF-8''termo.pdf"
        )
        assert downloaded.headers["x-content-type-options"] == "nosniff"

    def test_rejects_unsupported_content(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        response = db_client.post(
            f"/agreements/{agreement.id}/documents",
            headers=operator_headers,
            files={"file": ("termo.pdf", b"not a pdf", "application/pdf")},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Tipo de arquivo não aceito. Envie PDF, PNG ou JPEG."
        }

    def test_documents_require_office_staff(
        self,
        db_client: TestClient,
        client_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        response = db_client.get(
            f"/agreements/{agreement.id}/documents", headers=client_headers
        )

        assert response.status_code == 403

    def test_unknown_document_is_not_found(
        self,
        db_client: TestClient,
        operator_headers: dict[str, str],
        agreement: Agreement,
    ) -> None:
        response = db_client.get(
            f"/agreements/{agreement.id}/documents/{UNKNOWN_ID}",
            headers=operator_headers,
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Documento não encontrado."}

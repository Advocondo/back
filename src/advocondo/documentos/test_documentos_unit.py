from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.common.pdf import PdfSection, PdfTable
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.documentos.agreement_pdf import build_agreement_document, format_cnpj
from advocondo.documentos.errors import (
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidUrlError,
    UnsupportedDocumentTypeError,
)
from advocondo.documentos.models import AgreementPdf
from advocondo.documentos.rules import (
    DEFAULT_FILENAME,
    MAX_DOCUMENT_SIZE,
    MAX_FILENAME_LENGTH,
    MAX_URL_LENGTH,
    clean_filename,
    detect_content_type,
    filename_for_link,
    validate_document,
    validate_url,
)
from advocondo.parcelas.models import Installment
from advocondo.users.models import User

GENERATED_AT = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
TODAY = date(2026, 3, 2)
PDF = b"%PDF-1.7\n%termo de acordo\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 16


def make_agreement(**condominium_fields: str) -> Agreement:
    """An agreement in memory, as loaded from the database, with a 10% fee."""
    return Agreement(
        condominium=Condominium(name="Residencial Mirante", **condominium_fields),
        debtor=Debtor(name="José Simão", unit="Bloco B 304"),
        total_amount=Decimal("200.00"),
        fee_amount=Decimal("20.00"),
        fee_percentage=Decimal("10.00"),
        status=AgreementStatus.ACTIVE,
        created_at=datetime(2026, 1, 5, 2, 0, tzinfo=UTC),
        installments=[
            Installment(
                number=number,
                due_date=due_date,
                payment_date=payment_date,
                amount=Decimal("100.00"),
                condominium_amount=Decimal("90.00"),
                fee_amount=Decimal("10.00"),
            )
            for number, (due_date, payment_date) in enumerate(
                [(date(2026, 2, 10), date(2026, 2, 10)), (date(2026, 3, 10), None)],
                start=1,
            )
        ],
    )


def rows_of(agreement: Agreement, title: str) -> dict[str, str]:
    document = build_agreement_document(agreement, GENERATED_AT, TODAY)
    section = next(block for block in document.blocks if block.title == title)
    assert isinstance(section, PdfSection)
    return dict(section.rows)


class TestAgreementDocument:
    def test_agreement_section(self) -> None:
        """US24-CA01"""
        rows = rows_of(make_agreement(), "Acordo")

        assert rows == {
            "Situação": "Ativo",
            # 02:00 UTC on Jan 5 is still Jan 4 in Brasília.
            "Cadastrado em": "04/01/2026",
            "Valor total": "R$ 200,00",
            "Parcelas": "2",
            "Total pago": "R$ 100,00",
            "Saldo em aberto": "R$ 100,00",
            "Advogado responsável": "Não atribuído",
        }

    def test_responsible_lawyer_with_oab(self) -> None:
        agreement = make_agreement()
        agreement.responsible_lawyer = User(name="Marina Dias", oab_number="123456/DF")

        rows = rows_of(agreement, "Acordo")

        assert rows["Advogado responsável"] == "Marina Dias (OAB 123456/DF)"

    def test_installments_table(self) -> None:
        document = build_agreement_document(make_agreement(), GENERATED_AT, TODAY)

        table = document.blocks[-1]
        assert isinstance(table, PdfTable)
        assert list(table.rows) == [
            ("1", "10/02/2026", "R$ 100,00", "10/02/2026", "Pago"),
            ("2", "10/03/2026", "R$ 100,00", "-", "Em aberto"),
        ]
        assert table.footer == ("Total", "", "R$ 200,00", "", "")

    def test_condominium_with_cnpj_and_address(self) -> None:
        rows = rows_of(
            make_agreement(
                cnpj="11222333000181",
                street="Rua das Flores, 100",
                neighborhood="Asa Sul",
                city="Brasília",
                state="DF",
                zip_code="70000123",
            ),
            "Condomínio",
        )

        assert rows == {
            "Nome": "Residencial Mirante",
            "CNPJ": "11.222.333/0001-81",
            "Endereço": "Rua das Flores, 100, Asa Sul, Brasília/DF, CEP 70000-123",
        }

    def test_condominium_without_optional_data(self) -> None:
        assert rows_of(make_agreement(), "Condomínio") == {
            "Nome": "Residencial Mirante"
        }

    def test_no_fee_anywhere(self) -> None:
        """The Client downloads the same file (US24-CA03) and never sees fees (US16)."""
        document = build_agreement_document(make_agreement(), GENERATED_AT, TODAY)

        cells: list[str] = [document.title, document.subtitle]
        for block in document.blocks:
            if isinstance(block, PdfSection):
                cells.extend(cell for row in block.rows for cell in row)
            else:
                cells.extend(block.header)
                cells.extend(cell for row in block.rows for cell in row)
        text = "\n".join(cells)
        for forbidden in ("Honorários", "10,00%", "10%", "R$ 10,00", "R$ 20,00"):
            assert forbidden not in text
        assert "R$ 90,00" not in text


class TestFormatCnpj:
    @pytest.mark.parametrize(
        ("cnpj", "expected"),
        [
            pytest.param("11222333000181", "11.222.333/0001-81", id="numeric"),
            pytest.param("12ABC34501DE35", "12.ABC.345/01DE-35", id="alphanumeric"),
            pytest.param("123", "123", id="unexpected-length-kept"),
        ],
    )
    def test_mask(self, cnpj: str, expected: str) -> None:
        assert format_cnpj(cnpj) == expected


class TestAgreementPdfFileName:
    def test_uses_the_time_in_brazil(self) -> None:
        pdf = AgreementPdf(generated_at=datetime(2026, 3, 2, 1, 30, tzinfo=UTC))

        assert pdf.file_name == "acordo-20260301-223000.pdf"


class TestDetectContentType:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            pytest.param(PDF, "application/pdf", id="pdf"),
            pytest.param(PNG, "image/png", id="png"),
            pytest.param(JPEG, "image/jpeg", id="jpeg"),
            pytest.param(b"termo de acordo", None, id="plain-text"),
            pytest.param(b"MZ\x90\x00", None, id="executable"),
            pytest.param(b"", None, id="empty"),
        ],
    )
    def test_type_comes_from_the_content(
        self, content: bytes, expected: str | None
    ) -> None:
        """US21-CA01"""
        assert detect_content_type(content) == expected


class TestCleanFilename:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            pytest.param("termo.pdf", "termo.pdf", id="plain-name"),
            pytest.param("  termo.pdf  ", "termo.pdf", id="spaces-around"),
            pytest.param("../../etc/passwd", "passwd", id="unix-path"),
            pytest.param(r"C:\Users\ana\termo.pdf", "termo.pdf", id="windows-path"),
            pytest.param("termo\x00.pdf", "termo.pdf", id="control-character"),
            pytest.param("março.pdf", "março.pdf", id="accents"),
            pytest.param("a" * 300 + ".pdf", "a" * MAX_FILENAME_LENGTH, id="too-long"),
            pytest.param(None, DEFAULT_FILENAME, id="no-name"),
            pytest.param("", DEFAULT_FILENAME, id="empty-name"),
            pytest.param("..", DEFAULT_FILENAME, id="parent-folder"),
            pytest.param("pasta/", DEFAULT_FILENAME, id="only-a-folder"),
        ],
    )
    def test_only_a_safe_file_name_is_kept(
        self, filename: str | None, expected: str
    ) -> None:
        """US21-CA01"""
        assert clean_filename(filename) == expected


class TestValidateDocument:
    def test_valid_document_returns_its_type(self) -> None:
        """US21-CA01"""
        assert validate_document(PDF) == "application/pdf"

    def test_document_with_the_maximum_size_is_accepted(self) -> None:
        """US21-CA01"""
        content = b"%PDF-" + b"0" * (MAX_DOCUMENT_SIZE - 5)

        assert validate_document(content) == "application/pdf"

    @pytest.mark.parametrize(
        ("content", "error"),
        [
            pytest.param(b"", EmptyDocumentError, id="empty"),
            pytest.param(
                b"%PDF-" + b"0" * MAX_DOCUMENT_SIZE,
                DocumentTooLargeError,
                id="too-large",
            ),
            pytest.param(b"termo", UnsupportedDocumentTypeError, id="unsupported-type"),
        ],
    )
    def test_invalid_document_is_refused(
        self, content: bytes, error: type[Exception]
    ) -> None:
        """US21-CA01"""
        with pytest.raises(error):
            validate_document(content)


class TestValidateUrl:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            pytest.param(
                "https://drive.example.com/d/123",
                "https://drive.example.com/d/123",
                id="https",
            ),
            pytest.param("http://example.com", "http://example.com", id="http"),
            pytest.param(
                "HTTPS://Example.com/a", "HTTPS://Example.com/a", id="uppercase-scheme"
            ),
            pytest.param(
                "  https://example.com/a  ", "https://example.com/a", id="spaces-around"
            ),
        ],
    )
    def test_valid_link_is_kept(self, url: str, expected: str) -> None:
        """US21-CA01"""
        assert validate_url(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("", id="empty"),
            pytest.param("   ", id="blank"),
            pytest.param("javascript:alert(1)", id="script"),
            pytest.param("data:text/html,<b>oi</b>", id="data"),
            pytest.param("file:///etc/passwd", id="local-file"),
            pytest.param("ftp://example.com/termo.pdf", id="other-scheme"),
            pytest.param("example.com/termo.pdf", id="no-scheme"),
            pytest.param("https://", id="no-host"),
            pytest.param("https://exa mple.com/a", id="space-inside"),
            pytest.param("https://example.com/\x00", id="control-character"),
            pytest.param("http://[::1", id="malformed-host"),
            pytest.param("https://example.com/" + "a" * MAX_URL_LENGTH, id="too-long"),
        ],
    )
    def test_invalid_link_is_refused(self, url: str) -> None:
        """US21-CA01"""
        with pytest.raises(InvalidUrlError):
            validate_url(url)


class TestFilenameForLink:
    @pytest.mark.parametrize(
        ("url", "name", "expected"),
        [
            pytest.param(
                "https://example.com/d/1", "Termo assinado", "Termo assinado", id="name"
            ),
            pytest.param(
                "https://example.com/docs/termo%20final.pdf",
                None,
                "termo final.pdf",
                id="last-segment",
            ),
            pytest.param("https://example.com/pasta/", None, "pasta", id="folder-url"),
            pytest.param(
                "https://example.com/", None, "example.com", id="only-the-site"
            ),
            pytest.param("https://example.com/d/1", "   ", "1", id="blank-name"),
            pytest.param(
                "https://example.com/d/1",
                "../../x.pdf",
                "x.pdf",
                id="name-with-folders",
            ),
        ],
    )
    def test_link_gets_a_readable_name(
        self, url: str, name: str | None, expected: str
    ) -> None:
        """US21-CA01"""
        assert filename_for_link(url, name) == expected

import logging
import smtplib
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

import pytest

from advocondo.common import email as email_module
from advocondo.common.clock import get_clock, today_in_brazil
from advocondo.common.email import (
    EmailMessage,
    LogEmailSender,
    SmtpEmailSender,
    build_email_sender,
)
from advocondo.common.error_handlers import status_for
from advocondo.common.errors import (
    AppError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from advocondo.common.money import format_brl
from advocondo.common.normalization import comparable_text, keep_only_digits
from advocondo.common.passwords import PasswordHasher
from advocondo.common.pdf import (
    PdfDocument,
    PdfSection,
    PdfTable,
    format_date,
    format_money,
    render_pdf,
)
from advocondo.common.storage import (
    DatabaseStorage,
    FileUnavailableError,
    ObjectStorage,
    StoredFileMixin,
    build_file_storage,
)
from advocondo.common.tokens import generate_opaque_token, hash_token
from tests.support.pdf import pdf_text
from tests.support.settings import make_settings
from tests.support.storage import FakeS3Client

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class ExpiredLinkError(AuthenticationError):
    pass


hasher = PasswordHasher()


PASSWORD_HASH = hasher.hash("senha-correta")


MESSAGE = EmailMessage(to="ana@example.com", subject="Assunto", body="Corpo")


class FakeSmtp:
    instances: ClassVar[list["FakeSmtp"]] = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.address = (host, port)
        self.calls: list[str] = []
        self.sent: list[Any] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append("quit")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(f"login:{username}")

    def send_message(self, message: Any) -> None:
        self.sent.append(message)


def build_smtp_sender(**overrides: Any) -> SmtpEmailSender:
    options: dict[str, Any] = {
        "host": "smtp.example.com",
        "port": 587,
        "username": "usuario",
        "password": "segredo",
        "use_tls": True,
        "sender": "Advocondo <nao-responda@example.com>",
    }
    return SmtpEmailSender(**(options | overrides))


class TestClock:
    def test_system_clock_returns_an_aware_utc_datetime(self) -> None:
        assert get_clock().now().tzinfo == UTC


class TestErrorHandlers:
    @pytest.mark.parametrize(
        ("error", "status"),
        [
            pytest.param(ExpiredLinkError(), 401, id="authentication-subclass"),
            pytest.param(PermissionDeniedError(), 403, id="permission-denied"),
            pytest.param(NotFoundError(), 404, id="not-found"),
            pytest.param(ConflictError(), 409, id="conflict"),
            pytest.param(BusinessRuleError(), 422, id="business-rule"),
            pytest.param(AppError(), 400, id="unmapped"),
        ],
    )
    def test_each_error_maps_to_its_http_status(
        self, error: AppError, status: int
    ) -> None:
        assert status_for(error) == status

    def test_custom_message_replaces_the_default(self) -> None:
        assert (
            NotFoundError("Acordo não encontrado.").message == "Acordo não encontrado."
        )


class TestPasswords:
    def test_hash_does_not_contain_the_password(self) -> None:
        assert "senha-correta" not in PASSWORD_HASH

    @pytest.mark.parametrize(
        ("password", "expected"),
        [
            pytest.param("senha-correta", True, id="right-password"),
            pytest.param("senha-errada", False, id="wrong-password"),
            pytest.param("", False, id="empty-password"),
        ],
    )
    def test_verify_accepts_only_the_hashed_password(
        self, password: str, expected: bool
    ) -> None:
        assert hasher.verify(PASSWORD_HASH, password) is expected


class TestTokens:
    def test_generated_tokens_are_unique(self) -> None:
        assert generate_opaque_token() != generate_opaque_token()

    def test_hash_is_stable_and_does_not_contain_the_token(self) -> None:
        token = generate_opaque_token()

        assert hash_token(token) == hash_token(token)
        assert token not in hash_token(token)


class TestEmail:
    @pytest.fixture
    def fake_smtp(self, monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
        FakeSmtp.instances = []
        monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
        return FakeSmtp

    @pytest.mark.parametrize(
        ("overrides", "calls"),
        [
            pytest.param({}, ["starttls", "login:usuario", "quit"], id="tls-and-login"),
            pytest.param(
                {"use_tls": False, "username": None, "password": None},
                ["quit"],
                id="no-tls-no-login",
            ),
        ],
    )
    def test_smtp_sender_delivers_the_message(
        self, fake_smtp: type[FakeSmtp], overrides: dict[str, Any], calls: list[str]
    ) -> None:
        build_smtp_sender(**overrides).send(MESSAGE)

        smtp = fake_smtp.instances[0]
        sent = smtp.sent[0]
        assert smtp.address == ("smtp.example.com", 587)
        assert smtp.calls == calls
        assert (sent["From"], sent["To"], sent["Subject"]) == (
            "Advocondo <nao-responda@example.com>",
            "ana@example.com",
            "Assunto",
        )
        assert sent.get_content().strip() == "Corpo"

    def test_log_sender_writes_the_message_to_the_log(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO, logger="advocondo.common.email"):
            LogEmailSender().send(MESSAGE)

        assert "Para: ana@example.com\nAssunto: Assunto\n\nCorpo" in caplog.text

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            pytest.param(
                {"environment": "local"}, LogEmailSender, id="local-without-smtp"
            ),
            pytest.param(
                {
                    "environment": "producao",
                    "smtp_host": "smtp.example.com",
                    "email_from": "nao-responda@example.com",
                },
                SmtpEmailSender,
                id="smtp-configured",
            ),
        ],
    )
    def test_sender_is_chosen_from_the_settings(
        self, overrides: dict[str, Any], expected: type
    ) -> None:
        assert isinstance(build_email_sender(make_settings(**overrides)), expected)

    @pytest.mark.parametrize(
        ("overrides", "missing"),
        [
            pytest.param(
                {"environment": "producao"}, "SMTP_HOST", id="production-without-smtp"
            ),
            pytest.param(
                {"environment": "local", "smtp_host": "smtp.example.com"},
                "EMAIL_FROM",
                id="smtp-without-sender",
            ),
        ],
    )
    def test_incomplete_email_settings_are_refused(
        self, overrides: dict[str, Any], missing: str
    ) -> None:
        with pytest.raises(RuntimeError, match=missing):
            build_email_sender(make_settings(**overrides))

    def test_app_dependency_builds_the_sender_from_the_app_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(email_module, "get_settings", make_settings)

        assert isinstance(email_module.get_email_sender(), LogEmailSender)


class TestTodayInBrazil:
    @pytest.mark.parametrize(
        ("moment", "expected"),
        [
            pytest.param(
                datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
                date(2026, 10, 15),
                id="midday",
            ),
            pytest.param(
                datetime(2026, 10, 15, 3, 0, tzinfo=UTC),
                date(2026, 10, 15),
                id="midnight-in-brazil",
            ),
            pytest.param(
                datetime(2026, 10, 15, 2, 59, tzinfo=UTC),
                date(2026, 10, 14),
                id="one-minute-before-midnight-in-brazil",
            ),
        ],
    )
    def test_date_follows_brasilia_time(self, moment: datetime, expected: date) -> None:
        """US27-CA01"""
        assert today_in_brazil(moment) == expected


class TestNormalization:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param("(61) 91234-5678", "61912345678", id="phone-mask"),
            pytest.param("14.447.918/0001-98", "14447918000198", id="cnpj-mask"),
            pytest.param(None, None, id="none"),
            pytest.param(61912345678, 61912345678, id="not-text"),
        ],
    )
    def test_only_digits_are_kept_in_text(
        self, value: object, expected: object
    ) -> None:
        assert keep_only_digits(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param("  José   SIMÃO ", "jose simao", id="accents-case-spaces"),
            pytest.param("Conceição", "conceicao", id="cedilla"),
            pytest.param("ana", "ana", id="already-comparable"),
            pytest.param("   ", "", id="only-spaces"),
        ],
    )
    def test_comparable_text_ignores_accents_case_and_spaces(
        self, value: str, expected: str
    ) -> None:
        assert comparable_text(value) == expected


class TestFormatBrl:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param(Decimal("1234.56"), "R$ 1.234,56", id="thousands"),
            pytest.param(Decimal("1234567.8"), "R$ 1.234.567,80", id="millions"),
            pytest.param(Decimal(0), "R$ 0,00", id="zero"),
            pytest.param(Decimal(5), "R$ 5,00", id="whole-number"),
            pytest.param(Decimal("999.99"), "R$ 999,99", id="below-a-thousand"),
        ],
    )
    def test_amount_is_written_the_brazilian_way(
        self, value: Decimal, expected: str
    ) -> None:
        assert format_brl(value) == expected


class TestPdf:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param(Decimal(5500), "R$ 5.500,00", id="thousands"),
            pytest.param(Decimal("0.01"), "R$ 0,01", id="cents"),
            pytest.param(Decimal("1234567.8"), "R$ 1.234.567,80", id="millions"),
        ],
    )
    def test_format_money(self, value: Decimal, expected: str) -> None:
        assert format_money(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param(
                date(2026, 1, 5), "05/01/2026", id="single-digit-day-and-month"
            ),
            pytest.param(date(2026, 12, 31), "31/12/2026", id="end-of-year"),
            pytest.param(date(2028, 2, 29), "29/02/2028", id="leap-day"),
        ],
    )
    def test_format_date(self, value: date, expected: str) -> None:
        assert format_date(value) == expected

    @pytest.mark.parametrize(
        ("subtitle", "expected"),
        [
            pytest.param("", "Relatório", id="without-subtitle"),
            pytest.param("Gerado hoje", "Relatório\nGerado hoje", id="with-subtitle"),
        ],
    )
    def test_title_and_optional_subtitle(self, subtitle: str, expected: str) -> None:
        content = render_pdf(
            PdfDocument(title="Relatório", subtitle=subtitle, blocks=())
        )

        assert pdf_text(content).strip() == expected

    def test_render_writes_every_block(self) -> None:
        document = PdfDocument(
            title="Relatório",
            subtitle="Gerado hoje",
            blocks=(
                PdfSection("Dados", [("Nome", "Ação & <Cia>")]),
                PdfTable("Itens", header=("Nº", "Valor"), rows=[("1", "R$ 1,00")]),
            ),
        )

        content = render_pdf(document)

        assert content.startswith(b"%PDF")
        text = pdf_text(content)
        for expected in ("Relatório", "Gerado hoje", "Nome", "Nº", "R$ 1,00"):
            assert expected in text
        # Markup characters come out as typed (ReportLab splits them in text runs).
        assert "Ação & <Cia>" in text.replace("\n", "")


class StoredFile(StoredFileMixin):
    """A stored file outside the database, for the storage tests."""


BUCKET = "advocondo-arquivos"
KEY = "agreements/1/pdfs/2.pdf"


class TestFileStorage:
    def test_database_storage_keeps_the_bytes_in_the_row(self) -> None:
        file = StoredFile()

        DatabaseStorage().save(file, KEY, b"%PDF-1.4", "application/pdf")

        assert file.content == b"%PDF-1.4"
        assert file.storage_key is None
        assert file.size_bytes == 8
        assert file.content_type == "application/pdf"
        assert DatabaseStorage().load(file) == b"%PDF-1.4"

    def test_database_storage_cannot_read_a_file_in_the_bucket(self) -> None:
        file = StoredFile()
        file.content = None
        file.storage_key = KEY

        with pytest.raises(FileUnavailableError, match="S3_"):
            DatabaseStorage().load(file)

    def test_object_storage_puts_the_bytes_in_the_bucket(self) -> None:
        client = FakeS3Client()
        storage = ObjectStorage(cast("S3Client", client), BUCKET)
        file = StoredFile()

        storage.save(file, KEY, b"%PDF-1.4", "application/pdf")

        assert client.objects == {(BUCKET, KEY): b"%PDF-1.4"}
        assert client.content_types == {(BUCKET, KEY): "application/pdf"}
        assert file.content is None
        assert file.storage_key == KEY
        assert file.size_bytes == 8
        assert storage.load(file) == b"%PDF-1.4"

    def test_object_storage_still_reads_files_saved_in_the_database(self) -> None:
        """Files saved before the bucket was configured keep working."""
        file = StoredFile()
        DatabaseStorage().save(file, KEY, b"%PDF-antigo", "application/pdf")

        storage = ObjectStorage(cast("S3Client", FakeS3Client()), BUCKET)

        assert storage.load(file) == b"%PDF-antigo"

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            pytest.param({}, DatabaseStorage, id="database-by-default"),
            pytest.param(
                {
                    "s3_endpoint_url": "https://conta.r2.cloudflarestorage.com",
                    "s3_region": "auto",
                    "s3_bucket": BUCKET,
                    "s3_access_key_id": "chave",
                    "s3_secret_access_key": "segredo",  # gitleaks:allow (fake value)
                },
                ObjectStorage,
                id="bucket-when-configured",
            ),
        ],
    )
    def test_storage_is_chosen_from_the_settings(
        self, overrides: dict[str, Any], expected: type
    ) -> None:
        assert isinstance(build_file_storage(make_settings(**overrides)), expected)

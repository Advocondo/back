from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.common.pdf import PdfSection, PdfTable
from advocondo.condominios.models import Condominium
from advocondo.devedores.models import Debtor
from advocondo.documentos.agreement_pdf import build_agreement_document, format_cnpj
from advocondo.documentos.models import AgreementPdf
from advocondo.parcelas.models import Installment
from advocondo.users.models import User

GENERATED_AT = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
TODAY = date(2026, 3, 2)


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

"""What goes in the agreement PDF (US24-CA01).

The same file is downloaded by the office and by the condominium's Client users
(US24-CA03), so it never carries the office's fee: no `fee_amount`,
`fee_percentage` or `condominium_amount` (US16, EP06).
"""

from datetime import date, datetime
from decimal import Decimal

from advocondo.acordos.models import Agreement, AgreementStatus
from advocondo.common.clock import BRAZIL_TIMEZONE
from advocondo.common.pdf import (
    PdfDocument,
    PdfSection,
    PdfTable,
    format_date,
    format_money,
    render_pdf,
)
from advocondo.condominios.models import Condominium
from advocondo.parcelas.status import InstallmentStatus

AGREEMENT_STATUS_LABELS = {AgreementStatus.ACTIVE: "Ativo"}
INSTALLMENT_STATUS_LABELS = {
    InstallmentStatus.OPEN: "Em aberto",
    InstallmentStatus.PAID: "Pago",
    InstallmentStatus.OVERDUE: "Atrasado",
}
INSTALLMENT_HEADER = ("Nº", "Vencimento", "Valor", "Pagamento", "Situação")
NUMERIC_CNPJ_LENGTH = 14


def build_agreement_document(
    agreement: Agreement, generated_at: datetime, today: date
) -> PdfDocument:
    """`today` is the date in Brazil, used for the status of each installment."""
    installments = agreement.installments
    paid = sum((item.amount for item in installments if item.is_paid), Decimal(0))
    planned = sum((item.amount for item in installments), Decimal(0))
    lawyer = agreement.responsible_lawyer
    local_generated_at = generated_at.astimezone(BRAZIL_TIMEZONE)
    return PdfDocument(
        title="Acordo extrajudicial",
        subtitle=(
            f"Gerado em {format_date(local_generated_at)} às "
            f"{local_generated_at:%H:%M} (horário de Brasília)"
        ),
        blocks=(
            PdfSection("Condomínio", _condominium_rows(agreement.condominium)),
            PdfSection(
                "Devedor",
                [("Nome", agreement.debtor.name), ("Unidade", agreement.debtor.unit)],
            ),
            PdfSection(
                "Acordo",
                [
                    ("Situação", AGREEMENT_STATUS_LABELS[agreement.status]),
                    (
                        "Cadastrado em",
                        format_date(agreement.created_at.astimezone(BRAZIL_TIMEZONE)),
                    ),
                    ("Valor total", format_money(agreement.total_amount)),
                    ("Parcelas", str(len(installments))),
                    ("Total pago", format_money(paid)),
                    ("Saldo em aberto", format_money(agreement.total_amount - paid)),
                    (
                        "Advogado responsável",
                        f"{lawyer.name} (OAB {lawyer.oab_number})"
                        if lawyer is not None
                        else "Não atribuído",
                    ),
                ],
            ),
            PdfTable(
                "Parcelas",
                header=INSTALLMENT_HEADER,
                rows=[
                    (
                        str(item.number),
                        format_date(item.due_date),
                        format_money(item.amount),
                        format_date(item.payment_date) if item.payment_date else "-",
                        INSTALLMENT_STATUS_LABELS[item.status_on(today)],
                    )
                    for item in installments
                ],
                footer=("Total", "", format_money(planned), "", ""),
            ),
        ),
    )


def render_agreement_pdf(
    agreement: Agreement, generated_at: datetime, today: date
) -> bytes:
    return render_pdf(build_agreement_document(agreement, generated_at, today))


def format_cnpj(cnpj: str) -> str:
    """12345678000195 -> 12.345.678/0001-95; works for the alphanumeric CNPJ too."""
    if len(cnpj) != NUMERIC_CNPJ_LENGTH:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _condominium_rows(condominium: Condominium) -> list[tuple[str, str]]:
    rows = [("Nome", condominium.name)]
    if condominium.cnpj:
        rows.append(("CNPJ", format_cnpj(condominium.cnpj)))
    address = _address(condominium)
    if address:
        rows.append(("Endereço", address))
    return rows


def _address(condominium: Condominium) -> str:
    city = "/".join(part for part in (condominium.city, condominium.state) if part)
    zip_code = (
        f"CEP {condominium.zip_code[:5]}-{condominium.zip_code[5:]}"
        if condominium.zip_code
        else None
    )
    parts = (condominium.street, condominium.neighborhood, city, zip_code)
    return ", ".join(part for part in parts if part)

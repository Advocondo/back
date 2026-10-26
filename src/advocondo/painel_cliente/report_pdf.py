"""Fields shown in the condominium report downloaded by a Client (US39).

This document intentionally uses an allowlist of condominium and collection
status data. It never serializes the Agreement or Installment models, which also
contain the office's fee and operational fields.
"""

from datetime import date
from decimal import Decimal

from advocondo.acordos.models import Agreement
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


def render_condominium_report(
    client_name: str,
    condominium: Condominium,
    agreements: list[Agreement],
    today: date,
    period_label: str | None = None,
) -> bytes:
    rows: list[tuple[str, str, str, str, str, str]] = []
    total_paid = Decimal(0)
    total_balance = Decimal(0)

    for agreement in agreements:
        statuses = [item.status_on(today) for item in agreement.installments]
        overdue = sum(status == InstallmentStatus.OVERDUE for status in statuses)
        on_time = sum(status == InstallmentStatus.OPEN for status in statuses)
        paid_count = sum(status == InstallmentStatus.PAID for status in statuses)
        paid_amount = sum(
            (item.paid_amount for item in agreement.installments), Decimal(0)
        )
        balance = sum(
            (item.remaining_amount for item in agreement.installments), Decimal(0)
        )
        upcoming = [
            item.due_date
            for item in agreement.installments
            if item.status_on(today) == InstallmentStatus.OPEN
        ]
        total_paid += paid_amount
        total_balance += balance
        rows.append(
            (
                f"{agreement.debtor.name} — {agreement.debtor.unit}",
                "Atrasado" if overdue else "Em dia",
                f"{overdue} / {on_time} / {paid_count}",
                format_money(paid_amount),
                format_money(balance),
                format_date(min(upcoming)) if upcoming else "-",
            )
        )

    condominium_rows = [("Nome", condominium.name)]
    if condominium.cnpj:
        condominium_rows.append(("CNPJ", condominium.cnpj))

    subtitle = (
        f"Período: {period_label} | Fechado em {format_date(today)}"
        if period_label is not None
        else f"Cliente: {client_name} | Gerado em {format_date(today)}"
    )
    return render_pdf(
        PdfDocument(
            title="Relatório simplificado do condomínio",
            subtitle=subtitle,
            blocks=(
                PdfSection("Condomínio", condominium_rows),
                PdfSection(
                    "Resumo",
                    [
                        ("Acordos ativos", str(len(agreements))),
                        ("Total pago", format_money(total_paid)),
                        ("Saldo em aberto", format_money(total_balance)),
                    ],
                ),
                PdfTable(
                    "Acordos ativos",
                    header=(
                        "Devedor / unidade",
                        "Situação",
                        "Vencidas / em dia / pagas",
                        "Total pago",
                        "Saldo em aberto",
                        "Próximo vencimento",
                    ),
                    rows=rows,
                ),
            ),
        )
    )

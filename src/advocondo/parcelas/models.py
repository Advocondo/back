import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advocondo.acordos.models import MONEY, Agreement
from advocondo.common.models import TimestampsMixin, UuidPrimaryKeyMixin
from advocondo.db import Base
from advocondo.parcelas.status import InstallmentStatus, calculate_installment_status

# O número da NFS-e, a nota de serviço que o escritório emite, tem 15 dígitos
# (ano com 4 dígitos e sequencial com 11, no padrão nacional e no de BH).
INVOICE_NUMBER_LENGTH = 15


class Installment(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    """One monthly invoice of an agreement (US17)."""

    __tablename__ = "installments"
    __table_args__ = (
        UniqueConstraint(
            "agreement_id", "number", name="uq_installments_agreement_id_number"
        ),
        CheckConstraint("amount > 0", name="amount_is_positive"),
        CheckConstraint("number > 0", name="number_is_positive"),
        CheckConstraint(
            "condominium_amount >= 0 AND fee_amount >= 0", name="split_not_negative"
        ),
        CheckConstraint(
            "condominium_amount + fee_amount = amount", name="split_adds_up_to_amount"
        ),
        CheckConstraint(
            "paid_amount >= 0 AND paid_amount <= amount",
            name="paid_amount_within_amount",
        ),
        # Paga é a parcela quitada: pagamento parcial não marca a parcela como paga
        # (US28-CA01).
        CheckConstraint(
            "(payment_date IS NOT NULL) = (paid_amount = amount)",
            name="paid_only_when_fully_paid",
        ),
        # Uma nota fiscal tem sempre número e data de emissão (US29-CA01).
        CheckConstraint(
            "(invoice_number IS NULL) = (invoice_date IS NULL)",
            name="invoice_number_and_date_together",
        ),
    )

    agreement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agreements.id"), index=True
    )
    # 1 for the first installment, 2 for the second...
    number: Mapped[int]
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    # How the amount is split between the condominium and the office (US16).
    condominium_amount: Mapped[Decimal] = mapped_column(MONEY)
    fee_amount: Mapped[Decimal] = mapped_column(MONEY)
    # Filled when the payment is registered (US26). An installment with a payment
    # date can no longer be edited (US17-CA03).
    payment_date: Mapped[date | None] = mapped_column(Date)
    # Soma dos pagamentos recebidos, parciais ou não (US28).
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    # Nota fiscal emitida para a parcela paga (US29).
    invoice_number: Mapped[str | None] = mapped_column(String(INVOICE_NUMBER_LENGTH))
    invoice_date: Mapped[date | None] = mapped_column(Date)

    # Dá à listagem do mês o devedor e o condomínio da parcela (US25-CA01).
    agreement: Mapped[Agreement] = relationship(back_populates="installments")
    # Histórico dos pagamentos, na ordem em que foram registrados (US28-CA02).
    payments: Mapped[list["InstallmentPayment"]] = relationship(
        order_by="InstallmentPayment.created_at", cascade="all, delete-orphan"
    )

    @property
    def is_paid(self) -> bool:
        return self.payment_date is not None

    @property
    def has_payments(self) -> bool:
        return self.paid_amount > 0

    @property
    def remaining_amount(self) -> Decimal:
        return self.amount - self.paid_amount

    def receive(self, amount: Decimal, payment_date: date) -> None:
        """Registra um pagamento. Quando ele quita o saldo, a parcela fica paga nessa
        data (US26-CA01); antes disso, o saldo continua em aberto (US28-CA01)."""
        self.payments.append(
            InstallmentPayment(amount=amount, payment_date=payment_date)
        )
        self.paid_amount += amount
        if self.remaining_amount == 0:
            self.payment_date = payment_date

    def correct_payment_date(self, payment_date: date) -> None:
        """Troca a data da baixa, que é a do pagamento que quitou a parcela
        (US26-CA02)."""
        self.payments[-1].payment_date = payment_date
        self.payment_date = payment_date

    def reverse_payments(self) -> None:
        """Estorna todos os pagamentos: a parcela volta ao valor inteiro em aberto
        (US26-CA02)."""
        self.payments.clear()
        self.paid_amount = Decimal(0)
        self.payment_date = None

    def status_on(self, today: date) -> InstallmentStatus:
        return calculate_installment_status(self.due_date, self.payment_date, today)


class InstallmentPayment(UuidPrimaryKeyMixin, Base):
    """Um pagamento recebido de uma parcela, parcial ou não (US28-CA02)."""

    __tablename__ = "installment_payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_is_positive"),)

    installment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installments.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(MONEY)
    payment_date: Mapped[date] = mapped_column(Date)
    # clock_timestamp() em vez do now() do CreatedAtMixin: now() é o início da
    # transação, e pagamentos da mesma transação perderiam a ordem (como em
    # user_audit_logs, US11).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

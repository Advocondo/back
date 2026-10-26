import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from advocondo.common.clock import Clock, today_in_brazil
from advocondo.common.errors import PermissionDeniedError
from advocondo.painel_admin.export import build_installment_workbook
from advocondo.painel_admin.repository import AdminPanelRepository
from advocondo.painel_admin.schemas import (
    AdminDashboardSummary,
    AdminFinancialSummary,
    FinancialPeriod,
    TeamCommission,
    month_bounds,
)
from advocondo.parcelas.status import InstallmentStatus
from advocondo.users.models import Role, User


class AdminPanelService:
    def __init__(self, repository: AdminPanelRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def get_financial_summary(self, current_user: User) -> AdminFinancialSummary:
        if current_user.role != Role.ADMIN:
            raise PermissionDeniedError()

        today = today_in_brazil(self._clock.now())
        start, end = month_bounds(today)
        revenue = self._repository.office_total_revenue(start, end)
        commissions = self._repository.team_commissions(start, end)
        return AdminFinancialSummary(
            office_total_revenue=revenue,
            team_commissions=[
                TeamCommission(
                    user_id=user_id,
                    user_name=user_name,
                    commission=amount,
                )
                for user_id, user_name, amount in commissions
            ],
            period=FinancialPeriod(month=today.month, year=today.year),
        )

    def get_dashboard(
        self, current_user: User, year: int, month: int
    ) -> AdminDashboardSummary:
        if current_user.role != Role.ADMIN:
            raise PermissionDeniedError()

        period_start = date(year, month, 1)
        period_end = month_bounds(period_start)[1]
        # Um mês fechado é medido no último dia; o mês atual, hoje, para não contar
        # como atrasada a parcela que ainda vai vencer.
        last_day = date.fromordinal(period_end.toordinal() - 1)
        as_of_date = min(last_day, today_in_brazil(self._clock.now()))
        installments_due = self._repository.count_installments_due(
            period_start, period_end
        )
        overdue_installments = self._repository.count_overdue_installments_at(
            period_start, period_end, as_of_date
        )
        default_rate = (
            (Decimal(overdue_installments) * 100 / Decimal(installments_due)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if installments_due
            else Decimal("0.00")
        )
        return AdminDashboardSummary(
            active_agreements=self._repository.count_active_agreements(),
            monthly_default_rate=default_rate,
            overdue_installments=overdue_installments,
            installments_due=installments_due,
            paid_commissions=self._repository.paid_commissions(
                period_start, period_end
            ),
            period=FinancialPeriod(month=month, year=year),
        )

    def export_monthly_followup(
        self,
        current_user: User,
        year: int,
        month: int,
        *,
        condominium_id: uuid.UUID | None = None,
        responsible_lawyer_id: uuid.UUID | None = None,
        status: InstallmentStatus | None = None,
    ) -> bytes:
        if current_user.role != Role.ADMIN:
            raise PermissionDeniedError()

        period_start = date(year, month, 1)
        period_end = month_bounds(period_start)[1]
        as_of_date = today_in_brazil(self._clock.now())
        rows = self._repository.list_installments_for_export(
            period_start,
            period_end,
            as_of_date,
            condominium_id=condominium_id,
            responsible_lawyer_id=responsible_lawyer_id,
            status=status,
        )
        return build_installment_workbook(rows)

"""Notifica as parcelas que ficaram atrasadas (US30).

O status "Atrasado" é calculado a cada consulta e nunca gravado (US27), então nada
avisa quando uma parcela muda de status. Este comando, agendado no Coolify para
rodar uma vez por dia, logo depois da meia-noite de Brasília, cria as notificações:

    python -m advocondo.notificacoes.overdue
"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from advocondo.common.clock import Clock, get_clock, today_in_brazil
from advocondo.db import get_sessionmaker
from advocondo.notificacoes.models import Notification
from advocondo.notificacoes.repository import NotificationRepository
from advocondo.users.models import User, UserStatus
from advocondo.users.repository import UserRepository


def recipients(responsible_lawyer: User | None, admins: Sequence[User]) -> list[User]:
    """O advogado responsável pelo acordo, se estiver ativo, e os Administradores
    (US30-CA01). Quem for as duas coisas recebe uma notificação só."""
    users = list(admins)
    if (
        responsible_lawyer is not None
        and responsible_lawyer.status == UserStatus.ACTIVE
        and all(admin.id != responsible_lawyer.id for admin in admins)
    ):
        users.append(responsible_lawyer)
    return users


def notify_overdue_installments(session: Session, clock: Clock) -> int:
    """Cria as notificações das parcelas atrasadas que ainda não geraram uma e
    devolve quantas criou."""
    now = clock.now()
    notifications = NotificationRepository(session)
    admins = UserRepository(session).list_active_admins()
    new_notifications = [
        Notification(user_id=user.id, installment_id=installment.id, created_at=now)
        for installment in notifications.list_overdue_installments_without_notification(
            today_in_brazil(now)
        )
        for user in recipients(installment.agreement.responsible_lawyer, admins)
    ]
    notifications.add_all(new_notifications)
    session.commit()
    return len(new_notifications)


def main() -> None:
    with get_sessionmaker()() as session:
        created = notify_overdue_installments(session, get_clock())
    print(f"{created} notificações de parcela em atraso criadas.")


if __name__ == "__main__":
    main()

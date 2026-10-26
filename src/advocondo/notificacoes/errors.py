from advocondo.common.errors import NotFoundError


class NotificationNotFoundError(NotFoundError):
    message = "Notificação não encontrada."

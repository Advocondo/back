import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from advocondo.auth.models import UserSession
from advocondo.auth.repository import UserSessionRepository
from advocondo.common.clock import Clock
from advocondo.common.email import EmailMessage, EmailSender
from advocondo.common.passwords import MIN_PASSWORD_LENGTH, PasswordHasher
from advocondo.common.tokens import generate_opaque_token, hash_token
from advocondo.condominios.models import Condominium
from advocondo.users.errors import (
    AdminRoleNotAllowedError,
    CannotChangeOwnRoleError,
    CannotDeactivateSelfError,
    CurrentPasswordRequiredError,
    EmailAlreadyInUseError,
    FirstUserAlreadyCreatedError,
    InvalidInviteTokenError,
    OabNumberNotAllowedError,
    OabNumberRequiredError,
    PasswordTooShortError,
    TargetNotClientError,
    UnknownCondominiumsError,
    UserIsPendingError,
    UserNotFoundError,
    WrongCurrentPasswordError,
)
from advocondo.users.models import (
    AuditAction,
    Role,
    User,
    UserAuditLog,
    UserInvite,
    UserStatus,
)
from advocondo.users.repository import (
    UserAuditLogRepository,
    UserCondominiumRepository,
    UserInviteRepository,
    UserRepository,
)

INVITE_PAGE = "/convite"
logger = logging.getLogger(__name__)


class UserService:
    def __init__(
        self, session: Session, users: UserRepository, password_hasher: PasswordHasher
    ) -> None:
        self._session = session
        self._users = users
        self._password_hasher = password_hasher

    def create_first_admin(self, email: str, name: str, password: str) -> User:
        if self._users.is_any_registered():
            raise FirstUserAlreadyCreatedError()
        if len(password) < MIN_PASSWORD_LENGTH:
            raise PasswordTooShortError(MIN_PASSWORD_LENGTH)

        user = User(
            email=normalize_email(email),
            name=name.strip(),
            role=Role.ADMIN,
            status=UserStatus.ACTIVE,
            password_hash=self._password_hasher.hash(password),
        )
        self._users.add(user)
        self._session.commit()
        return user


@dataclass(frozen=True)
class ProfileChanges:
    name: str | None = None
    email: str | None = None
    new_password: str | None = None
    current_password: str | None = None


class ProfileService:
    def __init__(
        self,
        session: Session,
        users: UserRepository,
        user_sessions: UserSessionRepository,
        password_hasher: PasswordHasher,
    ) -> None:
        self._session = session
        self._users = users
        self._user_sessions = user_sessions
        self._password_hasher = password_hasher

    def update_profile(
        self, user_session: UserSession, changes: ProfileChanges
    ) -> User:
        user = user_session.user
        new_email = self._new_email(user, changes.email)
        if new_email is not None or changes.new_password is not None:
            self._confirm_current_password(user, changes.current_password)
        if new_email is not None and self._users.get_by_email(new_email) is not None:
            raise EmailAlreadyInUseError()

        if changes.name is not None:
            user.name = changes.name.strip()
        if new_email is not None:
            user.email = new_email
        if changes.new_password is not None:
            self._change_password(user_session, changes.new_password)
        self._session.commit()
        return user

    def _new_email(self, user: User, email: str | None) -> str | None:
        if email is None:
            return None
        normalized_email = normalize_email(email)
        return None if normalized_email == user.email else normalized_email

    def _confirm_current_password(
        self, user: User, current_password: str | None
    ) -> None:
        if current_password is None:
            raise CurrentPasswordRequiredError()
        if user.password_hash is None or not self._password_hasher.verify(
            user.password_hash, current_password
        ):
            raise WrongCurrentPasswordError()

    def _change_password(self, user_session: UserSession, new_password: str) -> None:
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise PasswordTooShortError(MIN_PASSWORD_LENGTH)
        user_session.user.password_hash = self._password_hasher.hash(new_password)
        self._user_sessions.delete_all_of_user_except(user_session)


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class InviteDetails:
    email: str
    name: str
    role: Role
    is_lawyer: bool
    oab_number: str | None


class InviteService:
    def __init__(
        self,
        session: Session,
        users: UserRepository,
        invites: UserInviteRepository,
        audit_logs: UserAuditLogRepository,
        password_hasher: PasswordHasher,
        email_sender: EmailSender,
        clock: Clock,
        invite_link_duration: timedelta,
        frontend_url: str,
    ) -> None:
        self._session = session
        self._users = users
        self._invites = invites
        self._audit_logs = audit_logs
        self._password_hasher = password_hasher
        self._email_sender = email_sender
        self._clock = clock
        self._invite_link_duration = invite_link_duration
        self._frontend_url = frontend_url

    def invite(self, invited_by: User, details: InviteDetails) -> User:
        if details.role == Role.ADMIN:
            raise AdminRoleNotAllowedError()
        self._check_oab(details.is_lawyer, details.oab_number)

        email = normalize_email(details.email)
        if self._users.get_by_email(email) is not None:
            raise EmailAlreadyInUseError()

        invited = User(
            email=email,
            name=details.name.strip(),
            role=details.role,
            status=UserStatus.PENDING,
            is_lawyer=details.is_lawyer,
            oab_number=details.oab_number if details.is_lawyer else None,
        )
        self._users.add(invited)

        token = generate_opaque_token()
        invite = UserInvite(
            user=invited,
            invited_by=invited_by,
            token_hash=hash_token(token),
            expires_at=self._clock.now() + self._invite_link_duration,
        )
        self._invites.add(invite)

        log = UserAuditLog(
            user=invited,
            actor=invited_by,
            action=AuditAction.INVITED,
            old_value=None,
            new_value=invited.role.value,
        )
        self._audit_logs.add(log)

        self._session.commit()

        self._send_invite_email(invited, token)
        return invited

    def accept_invite(self, token: str, password: str) -> User:
        invite = self._invites.get_by_token_hash(hash_token(token))
        if invite is None or invite.is_expired(self._clock.now()):
            raise InvalidInviteTokenError()
        user = invite.user
        if user.status != UserStatus.PENDING:
            raise InvalidInviteTokenError()
        if len(password) < MIN_PASSWORD_LENGTH:
            raise PasswordTooShortError(MIN_PASSWORD_LENGTH)

        user.password_hash = self._password_hasher.hash(password)
        user.status = UserStatus.ACTIVE
        self._invites.delete(invite)
        self._session.commit()
        return user

    def _check_oab(self, is_lawyer: bool, oab_number: str | None) -> None:
        if is_lawyer and oab_number is None:
            raise OabNumberRequiredError()
        if not is_lawyer and oab_number is not None:
            raise OabNumberNotAllowedError()

    def _send_invite_email(self, user: User, token: str) -> None:
        message = build_invite_email(
            user, self._invite_url(token), self._invite_link_duration
        )
        try:
            self._email_sender.send(message)
        except Exception:
            logger.exception("Falha ao enviar o e-mail de convite")

    def _invite_url(self, token: str) -> str:
        base_url = self._frontend_url.rstrip("/")
        return f"{base_url}{INVITE_PAGE}?{urlencode({'token': token})}"


def build_invite_email(
    user: User, invite_url: str, link_duration: timedelta
) -> EmailMessage:
    minutes = int(link_duration.total_seconds() // 60)
    body = (
        f"Olá, {user.name}.\n\n"
        "Você foi convidado para acessar o Advocondo. "
        f"Para definir sua senha, acesse o link abaixo em até {minutes} minutos:\n\n"
        f"{invite_url}\n\n"
        "Se você não esperava este convite, ignore este e-mail.\n"
    )
    return EmailMessage(to=user.email, subject="Convite de acesso", body=body)


class UserManagementService:
    def __init__(
        self,
        session: Session,
        users: UserRepository,
        audit_logs: UserAuditLogRepository,
        user_condominiums: UserCondominiumRepository,
    ) -> None:
        self._session = session
        self._users = users
        self._audit_logs = audit_logs
        self._user_condominiums = user_condominiums

    def change_status(
        self, admin: User, target_user_id: uuid.UUID, new_status: UserStatus
    ) -> User:
        user = self._users.get_by_id(target_user_id)
        if user is None:
            raise UserNotFoundError()
        if user.status == UserStatus.PENDING:
            raise UserIsPendingError()
        if user.id == admin.id and new_status == UserStatus.INACTIVE:
            raise CannotDeactivateSelfError()

        old_status = user.status
        user.status = new_status

        if old_status != new_status:
            log = UserAuditLog(
                user=user,
                actor=admin,
                action=AuditAction.STATUS_CHANGED,
                old_value=old_status.value,
                new_value=new_status.value,
            )
            self._audit_logs.add(log)

        self._session.commit()
        return user

    def change_role(
        self, admin: User, target_user_id: uuid.UUID, new_role: Role
    ) -> User:
        user = self._users.get_by_id(target_user_id)
        if user is None:
            raise UserNotFoundError()
        if user.id == admin.id and user.role != new_role:
            raise CannotChangeOwnRoleError()

        old_role = user.role
        user.role = new_role

        if old_role == Role.CLIENT and new_role != Role.CLIENT:
            # Condominium links only mean something for Clients (US10); dropping them
            # keeps old access from coming back if the user is made a Client again.
            self._user_condominiums.clear(user.id)

        if old_role != new_role:
            log = UserAuditLog(
                user=user,
                actor=admin,
                action=AuditAction.ROLE_CHANGED,
                old_value=old_role.value,
                new_value=new_role.value,
            )
            self._audit_logs.add(log)

        self._session.commit()
        return user


class AuditService:
    def __init__(
        self,
        users: UserRepository,
        audit_logs: UserAuditLogRepository,
    ) -> None:
        self._users = users
        self._audit_logs = audit_logs

    def list_user_history(self, user_id: uuid.UUID) -> list[UserAuditLog]:
        user = self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        return self._audit_logs.list_by_user(user_id)


class UserCondominiumService:
    def __init__(
        self,
        session: Session,
        users: UserRepository,
        user_condominiums: UserCondominiumRepository,
    ) -> None:
        self._session = session
        self._users = users
        self._user_condominiums = user_condominiums

    def list_condominiums(self, user_id: uuid.UUID) -> Sequence[Condominium]:
        self._ensure_is_client(self._users.get_by_id(user_id))
        return self._user_condominiums.list_condominiums_of(user_id)

    def replace_condominiums(
        self, user_id: uuid.UUID, condominium_ids: list[uuid.UUID]
    ) -> Sequence[Condominium]:
        """Sets the whole list of condominiums of a Client; an empty list unlinks all."""
        # The row lock serializes simultaneous edits of the same user's links.
        self._ensure_is_client(self._users.get_by_id_for_update(user_id))
        wanted = set(condominium_ids)
        missing = wanted - self._user_condominiums.existing_condominium_ids(wanted)
        if missing:
            raise UnknownCondominiumsError(sorted(missing, key=str))

        self._user_condominiums.replace(user_id, wanted)
        self._session.commit()
        return self._user_condominiums.list_condominiums_of(user_id)

    def _ensure_is_client(self, user: User | None) -> None:
        if user is None:
            raise UserNotFoundError()
        if user.role != Role.CLIENT:
            raise TargetNotClientError()

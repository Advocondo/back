"""Deletes expired sessions and password reset links (#55).

Expired rows give no access, but nothing else deletes them unless the user resets
the password, so the tables would only grow. Scheduled daily in Coolify:

    python -m advocondo.auth.cleanup
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from advocondo.auth.repository import PasswordResetLinkRepository, UserSessionRepository
from advocondo.common.clock import Clock, get_clock
from advocondo.config import get_settings
from advocondo.db import get_sessionmaker

# A reset link counts towards the request limit while it was created within the
# request window, and it never expires before it was created. Keeping it for the
# window after it expired is enough; a day leaves a margin for a longer window.
MIN_EXPIRED_RESET_LINK_RETENTION = timedelta(hours=24)


@dataclass(frozen=True)
class CleanupResult:
    sessions: int
    reset_links: int


def expired_reset_link_retention(request_window: timedelta) -> timedelta:
    return max(MIN_EXPIRED_RESET_LINK_RETENTION, request_window)


def delete_expired(
    session: Session, clock: Clock, request_window: timedelta
) -> CleanupResult:
    now = clock.now()
    sessions = UserSessionRepository(session).delete_expired(now)
    reset_links = PasswordResetLinkRepository(session).delete_expired_before(
        now - expired_reset_link_retention(request_window)
    )
    session.commit()
    return CleanupResult(sessions=sessions, reset_links=reset_links)


def main() -> None:
    request_window = get_settings().password_reset_request_window
    with get_sessionmaker()() as session:
        result = delete_expired(session, get_clock(), request_window)
    print(
        f"{result.sessions} sessões e {result.reset_links} links de redefinição "
        "expirados apagados."
    )


if __name__ == "__main__":
    main()

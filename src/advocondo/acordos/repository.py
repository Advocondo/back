from sqlalchemy.orm import Session

from advocondo.acordos.models import Agreement


class AgreementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, agreement: Agreement) -> None:
        """Inserts a new agreement or writes the changes of an existing one."""
        self._session.add(agreement)
        self._session.flush()

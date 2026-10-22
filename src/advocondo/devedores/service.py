import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.orm import Session

from advocondo.condominios.errors import CondominiumNotFoundError
from advocondo.condominios.repository import CondominiumRepository
from advocondo.devedores.errors import (
    ContactRequiredError,
    DebtorNotFoundError,
    SimilarDebtorsFoundError,
)
from advocondo.devedores.models import Debtor
from advocondo.devedores.repository import DebtorRepository
from advocondo.devedores.schemas import DebtorCreateRequest, DebtorUpdateRequest
from advocondo.devedores.similarity import find_similar_debtors
from advocondo.devedores.spreadsheet import (
    COLUMNS,
    ImportRowStatus,
    SpreadsheetRow,
    read_rows,
)


@dataclass
class ImportRow:
    number: int
    values: dict[str, str | None]
    errors: list[str] = field(default_factory=list)
    similar_debtors: list[Debtor] = field(default_factory=list)
    repeats_row: int | None = None

    @property
    def status(self) -> ImportRowStatus:
        if self.errors:
            return ImportRowStatus.INVALID
        if self.similar_debtors or self.repeats_row is not None:
            return ImportRowStatus.SIMILAR
        return ImportRowStatus.VALID


@dataclass(frozen=True)
class ImportResult:
    confirmed: bool
    imported: int
    rows: list[ImportRow]


class DebtorService:
    def __init__(
        self,
        session: Session,
        debtors: DebtorRepository,
        condominiums: CondominiumRepository,
    ) -> None:
        self._session = session
        self._debtors = debtors
        self._condominiums = condominiums

    def register(self, request: DebtorCreateRequest) -> Debtor:
        """Registers a debtor once, to be reused in every agreement with them."""
        if self._condominiums.get(request.condominium_id) is None:
            raise CondominiumNotFoundError()
        ensure_has_a_contact(request.phone, request.email)
        if not request.confirm_duplicate:
            self._warn_about_similar_debtors(request)

        debtor = Debtor(**request.model_dump(exclude={"confirm_duplicate"}))
        self._debtors.save(debtor)
        self._session.commit()
        return debtor

    def get(self, debtor_id: uuid.UUID) -> Debtor:
        debtor = self._debtors.get(debtor_id)
        if debtor is None:
            raise DebtorNotFoundError()
        return debtor

    def search(
        self,
        condominium_id: uuid.UUID | None,
        text: str | None,
        limit: int,
        offset: int,
    ) -> Sequence[Debtor]:
        search_text = text.strip() if text else None
        return self._debtors.search(condominium_id, search_text or None, limit, offset)

    def update(self, debtor_id: uuid.UUID, request: DebtorUpdateRequest) -> Debtor:
        debtor = self.get(debtor_id)
        changes = request.model_dump(exclude_unset=True)
        ensure_has_a_contact(
            changes.get("phone", debtor.phone), changes.get("email", debtor.email)
        )
        for field_name, new_value in changes.items():
            setattr(debtor, field_name, new_value)
        self._debtors.save(debtor)
        self._session.commit()
        return debtor

    def import_spreadsheet(
        self, condominium_id: uuid.UUID, content: bytes, *, confirm: bool
    ) -> ImportResult:
        """Checks every row and, once confirmed, registers the valid ones (US14).

        Without `confirm` nothing is saved: the user sees the rows with errors first.
        """
        if self._condominiums.get(condominium_id) is None:
            raise CondominiumNotFoundError()
        registered = self._debtors.list_by_condominium(condominium_id)
        accepted: dict[int, Debtor] = {}
        rows = []
        for spreadsheet_row in read_rows(content):
            row, debtor = check_row(
                condominium_id, spreadsheet_row, registered, accepted
            )
            rows.append(row)
            if debtor is not None:
                accepted[row.number] = debtor

        if confirm:
            for debtor in accepted.values():
                self._debtors.save(debtor)
            self._session.commit()
        return ImportResult(
            confirmed=confirm, imported=len(accepted) if confirm else 0, rows=rows
        )

    def _warn_about_similar_debtors(self, request: DebtorCreateRequest) -> None:
        similar_debtors = find_similar_debtors(
            request.name,
            request.unit,
            self._debtors.list_by_condominium(request.condominium_id),
        )
        if similar_debtors:
            raise SimilarDebtorsFoundError(similar_debtors)


def ensure_has_a_contact(phone: str | None, email: str | None) -> None:
    if phone is None and email is None:
        raise ContactRequiredError()


def check_row(
    condominium_id: uuid.UUID,
    spreadsheet_row: SpreadsheetRow,
    registered: Sequence[Debtor],
    accepted: dict[int, Debtor],
) -> tuple[ImportRow, Debtor | None]:
    """The row with its problems, and the debtor to register when it has none.

    `accepted` are the debtors of the earlier valid rows, by row number.
    """
    row = ImportRow(spreadsheet_row.number, spreadsheet_row.values)
    try:
        request = DebtorCreateRequest.model_validate(
            {"condominium_id": condominium_id, **spreadsheet_row.values}
        )
        ensure_has_a_contact(request.phone, request.email)
    except ValidationError as error:
        row.errors = invalid_field_messages(error)
        return row, None
    except ContactRequiredError as error:
        row.errors = [error.message]
        return row, None

    row.similar_debtors = find_similar_debtors(request.name, request.unit, registered)
    row.repeats_row = next(
        (
            number
            for number, debtor in accepted.items()
            if find_similar_debtors(request.name, request.unit, [debtor])
        ),
        None,
    )
    if row.status is not ImportRowStatus.VALID:
        return row, None
    return row, Debtor(**request.model_dump(exclude={"confirm_duplicate"}))


def invalid_field_messages(error: ValidationError) -> list[str]:
    """One message per refused column, in the spreadsheet order."""
    refused_fields = {
        str(detail["loc"][0]) for detail in error.errors() if detail["loc"]
    }
    return [
        column.invalid_message for column in COLUMNS if column.field in refused_fields
    ]

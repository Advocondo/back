from collections.abc import Iterator

import pytest

from advocondo.common.email import get_email_sender
from advocondo.main import app
from tests.support.email import Outbox


@pytest.fixture
def outbox() -> Iterator[Outbox]:
    """Captures the e-mails the API sends instead of delivering them."""
    captured = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: captured
    try:
        yield captured
    finally:
        app.dependency_overrides.pop(get_email_sender, None)

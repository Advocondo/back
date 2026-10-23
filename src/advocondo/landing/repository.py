import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from advocondo.landing.models import LandingBlock, LandingImage


class LandingBlockRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> Sequence[LandingBlock]:
        return self._session.scalars(select(LandingBlock)).all()

    def save(self, block: LandingBlock) -> None:
        self._session.add(block)
        self._session.flush()


class LandingImageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, image_id: uuid.UUID) -> LandingImage | None:
        return self._session.get(LandingImage, image_id)

    def existing_ids(self, image_ids: set[uuid.UUID]) -> set[uuid.UUID]:
        """Loads only the ids, never the image bytes."""
        query = select(LandingImage.id).where(LandingImage.id.in_(image_ids))
        return set(self._session.scalars(query))

    def save(self, image: LandingImage) -> None:
        self._session.add(image)
        self._session.flush()

    def delete(self, image_ids: set[uuid.UUID]) -> None:
        self._session.execute(
            delete(LandingImage).where(LandingImage.id.in_(image_ids))
        )

import uuid
from typing import BinaryIO

from sqlalchemy.orm import Session

from advocondo.landing.errors import (
    LandingImageInUseError,
    LandingImageNotFoundError,
    LandingImageTooLargeError,
    UnknownLandingImageError,
    UnsupportedLandingImageError,
)
from advocondo.landing.images import detect_media_type
from advocondo.landing.models import LandingBlock, LandingBlockKey, LandingImage
from advocondo.landing.repository import LandingBlockRepository, LandingImageRepository
from advocondo.landing.schemas import LandingContent, LandingUpdateRequest

BYTES_PER_KILOBYTE = 1024


class LandingService:
    def __init__(
        self,
        session: Session,
        blocks: LandingBlockRepository,
        images: LandingImageRepository,
        max_image_kilobytes: int,
    ) -> None:
        self._session = session
        self._blocks = blocks
        self._images = images
        self._max_image_kilobytes = max_image_kilobytes

    def get_content(self) -> LandingContent:
        return content_of(self._load_blocks())

    def update(self, request: LandingUpdateRequest) -> LandingContent:
        """Replaces the sections sent; the change is public as soon as it is saved."""
        blocks = self._load_blocks()
        current = content_of(blocks)
        changes = request.changed_blocks()
        updated = current.model_copy(update=changes)
        self._ensure_images_exist(updated.image_ids() - current.image_ids())
        for name, content in changes.items():
            block = blocks[LandingBlockKey(name)]
            block.content = content.model_dump(mode="json")
            self._blocks.save(block)
        self._delete_images(current.image_ids() - updated.image_ids())
        self._session.commit()
        return updated

    def upload_image(self, file: BinaryIO) -> LandingImage:
        """Stores an image to be used by a section, such as a team member's photo."""
        max_bytes = self._max_image_kilobytes * BYTES_PER_KILOBYTE
        # One byte over the limit is enough to refuse the file without reading it all.
        data = file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise LandingImageTooLargeError(self._max_image_kilobytes)
        media_type = detect_media_type(data)
        if media_type is None:
            raise UnsupportedLandingImageError()
        image = LandingImage(media_type=media_type, data=data)
        self._images.save(image)
        self._session.commit()
        return image

    def get_image(self, image_id: uuid.UUID) -> LandingImage:
        image = self._images.get(image_id)
        if image is None:
            raise LandingImageNotFoundError()
        return image

    def delete_image(self, image_id: uuid.UUID) -> None:
        """Discards an image uploaded but never saved in a section.

        Images replaced or removed from a section are deleted when the section is saved.
        """
        if not self._images.existing_ids({image_id}):
            raise LandingImageNotFoundError()
        if image_id in self.get_content().image_ids():
            raise LandingImageInUseError()
        self._images.delete({image_id})
        self._session.commit()

    def _load_blocks(self) -> dict[LandingBlockKey, LandingBlock]:
        return {block.key: block for block in self._blocks.list()}

    def _ensure_images_exist(self, image_ids: set[uuid.UUID]) -> None:
        if image_ids and self._images.existing_ids(image_ids) != image_ids:
            raise UnknownLandingImageError()

    def _delete_images(self, image_ids: set[uuid.UUID]) -> None:
        if image_ids:
            self._images.delete(image_ids)


def content_of(blocks: dict[LandingBlockKey, LandingBlock]) -> LandingContent:
    # Every section has a row since the migration that created the table, which also
    # wrote the initial content.
    return LandingContent.model_validate(
        {key: block.content for key, block in blocks.items()}
    )

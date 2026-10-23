import enum
from typing import Any

from sqlalchemy import LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.common.models import (
    CreatedAtMixin,
    TimestampsMixin,
    UuidPrimaryKeyMixin,
    string_enum,
)
from advocondo.db import Base


class LandingBlockKey(enum.StrEnum):
    """The fixed sections of the landing page that the Administrator edits (US04)."""

    HERO = "hero"
    PRACTICE_AREAS = "practice_areas"
    ONLINE_SERVICE = "online_service"
    CONDOMINIUM_ADVISORY = "condominium_advisory"
    REVIEWS = "reviews"
    WHY_US = "why_us"
    TEAM = "team"
    CONTACT_FORM = "contact_form"
    VISIT = "visit"
    CONTACT = "contact"


class ImageMediaType(enum.StrEnum):
    PNG = "image/png"
    JPEG = "image/jpeg"
    WEBP = "image/webp"


class LandingBlock(UuidPrimaryKeyMixin, TimestampsMixin, Base):
    """The content of one section. The migration that created the table wrote one row
    per section with the initial content, so the site is complete right after the
    deploy."""

    __tablename__ = "landing_blocks"

    key: Mapped[LandingBlockKey] = mapped_column(
        string_enum(LandingBlockKey, name="landing_block_key"), unique=True
    )
    # Validated by the section's schema before it is written.
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)


class LandingImage(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """An image shown on the landing page, such as a team member's photo.

    Images are never changed: a new photo is a new image, so it can be cached forever.
    """

    __tablename__ = "landing_images"

    media_type: Mapped[ImageMediaType] = mapped_column(
        string_enum(ImageMediaType, name="image_media_type")
    )
    data: Mapped[bytes] = mapped_column(LargeBinary)

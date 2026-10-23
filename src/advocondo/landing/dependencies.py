from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.config import Settings, get_settings
from advocondo.db import get_session
from advocondo.landing.repository import LandingBlockRepository, LandingImageRepository
from advocondo.landing.service import LandingService


def get_landing_service(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LandingService:
    return LandingService(
        session=session,
        blocks=LandingBlockRepository(session),
        images=LandingImageRepository(session),
        max_image_kilobytes=settings.landing_image_max_kilobytes,
    )

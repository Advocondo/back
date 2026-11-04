from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.common.email import EmailSender, get_email_sender
from advocondo.config import Settings, get_settings
from advocondo.db import get_session
from advocondo.landing.captcha import CaptchaVerifier, get_captcha_verifier
from advocondo.landing.contact import ContactService
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


def get_contact_service(
    landing: Annotated[LandingService, Depends(get_landing_service)],
    captcha: Annotated[CaptchaVerifier, Depends(get_captcha_verifier)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> ContactService:
    return ContactService(landing=landing, captcha=captcha, email_sender=email_sender)

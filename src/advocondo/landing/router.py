import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from advocondo.landing.dependencies import get_landing_service
from advocondo.landing.models import ImageMediaType
from advocondo.landing.schemas import (
    LandingContent,
    LandingImageResponse,
    LandingUpdateRequest,
)
from advocondo.landing.service import LandingService
from advocondo.users.dependencies import require_admin

# An image never changes (a new photo gets a new id), so browsers may keep it forever.
IMAGE_CACHE_CONTROL = "public, max-age=31536000, immutable"

# Reading the page and its images is public: they are shown to site visitors (US01).
router = APIRouter(prefix="/landing", tags=["landing"])
admin_only = [Depends(require_admin)]

LandingServiceDependency = Annotated[LandingService, Depends(get_landing_service)]


@router.get("")
def get_landing(landing_service: LandingServiceDependency) -> LandingContent:
    return landing_service.get_content()


@router.patch("", dependencies=admin_only)
def update_landing(
    request: LandingUpdateRequest, landing_service: LandingServiceDependency
) -> LandingContent:
    return landing_service.update(request)


@router.post("/images", status_code=status.HTTP_201_CREATED, dependencies=admin_only)
def upload_landing_image(
    file: Annotated[UploadFile, File(description="Imagem PNG, JPEG ou WebP")],
    landing_service: LandingServiceDependency,
) -> LandingImageResponse:
    image = landing_service.upload_image(file.file)
    return LandingImageResponse(id=image.id)


@router.get(
    "/images/{image_id}",
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "content": {media_type: {} for media_type in ImageMediaType}
        }
    },
)
def get_landing_image(
    image_id: uuid.UUID, landing_service: LandingServiceDependency
) -> Response:
    image = landing_service.get_image(image_id)
    return Response(
        image.data,
        media_type=image.media_type,
        headers={
            "Cache-Control": IMAGE_CACHE_CONTROL,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=admin_only,
)
def delete_landing_image(
    image_id: uuid.UUID, landing_service: LandingServiceDependency
) -> None:
    landing_service.delete_image(image_id)

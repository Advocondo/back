from advocondo.landing.models import ImageMediaType

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
RIFF_SIGNATURE = b"RIFF"
WEBP_SIGNATURE = b"WEBP"
WEBP_SIGNATURE_OFFSET = 8


def detect_media_type(data: bytes) -> ImageMediaType | None:
    """Reads the file signature instead of trusting the name or the Content-Type sent.

    SVG is not accepted: it can carry scripts and is served from the API's own domain.
    """
    if data.startswith(PNG_SIGNATURE):
        return ImageMediaType.PNG
    if data.startswith(JPEG_SIGNATURE):
        return ImageMediaType.JPEG
    webp_end = WEBP_SIGNATURE_OFFSET + len(WEBP_SIGNATURE)
    if (
        data.startswith(RIFF_SIGNATURE)
        and data[WEBP_SIGNATURE_OFFSET:webp_end] == WEBP_SIGNATURE
    ):
        return ImageMediaType.WEBP
    return None

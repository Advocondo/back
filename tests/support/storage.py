import io
from typing import Any


class FakeS3Client:
    """Keeps the objects in memory, in place of boto3's S3 client (no network)."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.content_types: dict[tuple[str, str], str] = {}

    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> dict[str, Any]:
        self.objects[Bucket, Key] = Body
        self.content_types[Bucket, Key] = ContentType
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": io.BytesIO(self.objects[Bucket, Key])}

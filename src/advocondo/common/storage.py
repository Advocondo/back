"""Where stored files keep their bytes: generated PDFs and uploaded documents.

Each file has a row in the database, with its metadata (`StoredFileMixin`). The
bytes go either into that same row (default) or into an S3-compatible bucket, when
the S3_ variables are set (docs/documentos.md). Reading looks at the row, not at
the current configuration, so files saved before the bucket was turned on are
still served.
"""

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Protocol

import boto3
from fastapi import Depends
from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from advocondo.config import Settings, get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

MAX_CONTENT_TYPE_LENGTH = 100
MAX_STORAGE_KEY_LENGTH = 500


class StoredFileMixin:
    """Columns of a stored file. Exactly one of `content` and `storage_key` is set."""

    content_type: Mapped[str] = mapped_column(String(MAX_CONTENT_TYPE_LENGTH))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Deferred: listings load only the metadata, never the bytes.
    content: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    # Key of the object in the bucket; empty when the bytes are in `content`.
    storage_key: Mapped[str | None] = mapped_column(String(MAX_STORAGE_KEY_LENGTH))


class FileUnavailableError(RuntimeError):
    """The file is in a bucket the API is no longer configured to read."""


class FileStorage(Protocol):
    def save(
        self, file: StoredFileMixin, key: str, content: bytes, content_type: str
    ) -> None:
        """Keeps `content` and fills the file's columns. `key` must be unique."""
        ...

    def load(self, file: StoredFileMixin) -> bytes: ...


def _fill_metadata(file: StoredFileMixin, content: bytes, content_type: str) -> None:
    file.content_type = content_type
    file.size_bytes = len(content)


class DatabaseStorage:
    """Keeps the bytes in the file's own row (bytea)."""

    def save(
        self, file: StoredFileMixin, key: str, content: bytes, content_type: str
    ) -> None:
        _fill_metadata(file, content, content_type)
        file.content = content
        file.storage_key = None

    def load(self, file: StoredFileMixin) -> bytes:
        if file.content is None:
            raise FileUnavailableError(
                f"O arquivo {file.storage_key} está no bucket, mas as variáveis S3_ "
                "não estão definidas."
            )
        return file.content


class ObjectStorage:
    """Keeps the bytes in an S3-compatible bucket (Amazon S3, Cloudflare R2,
    Backblaze B2). The API reads them back and serves them itself, so the access
    rules stay in the API instead of in a public or presigned URL."""

    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def save(
        self, file: StoredFileMixin, key: str, content: bytes, content_type: str
    ) -> None:
        # The object is written before the row is committed. If the commit fails,
        # an orphan object is left in the bucket, which is harmless.
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=content, ContentType=content_type
        )
        _fill_metadata(file, content, content_type)
        file.content = None
        file.storage_key = key

    def load(self, file: StoredFileMixin) -> bytes:
        if file.content is not None:
            return file.content
        assert file.storage_key is not None  # one of the two is always set
        response = self._client.get_object(Bucket=self._bucket, Key=file.storage_key)
        return response["Body"].read()


@lru_cache
def _s3_client(
    endpoint_url: str | None, region: str, access_key_id: str, secret_access_key: str
) -> "S3Client":
    """Creating a client is slow, so one is kept per configuration."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )


def build_file_storage(settings: Settings) -> FileStorage:
    if not settings.uses_object_storage:
        return DatabaseStorage()
    # All set when the bucket is: Settings refuses a partial configuration.
    assert settings.s3_bucket is not None
    assert settings.s3_region is not None
    assert settings.s3_access_key_id is not None
    assert settings.s3_secret_access_key is not None
    client = _s3_client(
        settings.s3_endpoint_url,
        settings.s3_region,
        settings.s3_access_key_id,
        settings.s3_secret_access_key,
    )
    return ObjectStorage(client, settings.s3_bucket)


def get_file_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileStorage:
    return build_file_storage(settings)

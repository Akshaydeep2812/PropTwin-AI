import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError

IMAGE_SIGNATURES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}
PDF_SIGNATURE = b"%PDF-"


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    content_type: str
    size_bytes: int
    sha256: str


def sniff_content_type(data: bytes) -> str | None:
    """Trusts the file's bytes, never the client-supplied name or content type."""
    for signature, content_type in IMAGE_SIGNATURES.items():
        if data.startswith(signature):
            return content_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(PDF_SIGNATURE):
        return "application/pdf"
    return None


class LocalStorage:
    """Local disk backend. Keys are server-generated, so a client filename can never reach the path."""

    def __init__(self, root: Path):
        self.root = root

    def save(self, data: bytes, allowed_types: set[str], prefix: str) -> StoredFile:
        settings = get_settings()
        if not data:
            raise AppError(422, "empty_file", "The uploaded file is empty.")
        if len(data) > settings.max_upload_bytes:
            raise AppError(413, "file_too_large", f"Files may be at most {settings.max_upload_bytes // (1024 * 1024)} MB.")
        content_type = sniff_content_type(data)
        if content_type not in allowed_types:
            raise AppError(415, "unsupported_file_type", "This file type is not allowed.")
        key = f"{prefix}/{uuid.uuid4().hex}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredFile(key, content_type, len(data), hashlib.sha256(data).hexdigest())

    def read(self, storage_key: str) -> bytes:
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise AppError(404, "file_not_found", "The stored file is missing.")
        return path.read_bytes()


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)

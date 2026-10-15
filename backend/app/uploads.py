from fastapi import UploadFile

from app.config import get_settings
from app.errors import api_error

SCAN_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"})
PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


def sniff_content_type(data: bytes) -> str | None:
    """Detect the real type from magic bytes; the client-declared type is not trusted."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def read_upload(file: UploadFile, allowed: frozenset[str]) -> tuple[bytes, str]:
    """Read an uploaded file with a size cap and return (bytes, detected content type)."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise api_error(413, "file_too_large", f"Файл больше {get_settings().max_upload_mb} МБ")
    if not data:
        raise api_error(422, "empty_file", "Файл пуст")
    content_type = sniff_content_type(data)
    if content_type is None or content_type not in allowed:
        raise api_error(415, "unsupported_media_type", "Допустимы файлы JPEG, PNG, WebP и PDF")
    return data, content_type


def read_csv_upload(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise api_error(413, "file_too_large", f"Файл больше {get_settings().max_upload_mb} МБ")
    if not data:
        raise api_error(422, "empty_file", "Файл пуст")
    return data

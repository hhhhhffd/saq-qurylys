"""Evidence storage: MinIO (S3) with Object Lock, sha256 and optional RFC 3161 timestamp."""

import hashlib
import io
import logging
import mimetypes
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from urllib.parse import urlparse

import httpx
from asn1crypto import algos, tsp
from minio import Minio
from minio.error import S3Error
from minio.retention import Retention
from sqlalchemy.orm import Session
from urllib3.response import BaseHTTPResponse

from app.config import get_settings
from app.models import Evidence
from app.models.enums import EvidenceKind, LockMode

logger = logging.getLogger(__name__)

_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
    "multipart/related": ".mhtml",
    "message/rfc822": ".mhtml",
    "application/x-mimearchive": ".mhtml",
}
# Only these are rendered inline by the content endpoint; everything else is a download.
INLINE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"})

TSA_TIMEOUT_S = 10
STREAM_CHUNK_BYTES = 64 * 1024

_bucket_ready = False


@dataclass(frozen=True)
class EvidenceLink:
    """The single entity an evidence item belongs to."""

    ad_post_id: int | None = None
    document_id: int | None = None
    inspection_id: int | None = None
    signal_card_id: int | None = None

    def owner(self) -> tuple[str, int]:
        owners = [(name, value) for name, value in vars(self).items() if value is not None]
        if len(owners) != 1:
            raise ValueError("EvidenceLink must reference exactly one entity")
        return owners[0]


def extension_for(content_type: str) -> str:
    base = content_type.split(";")[0].strip().lower()
    return _EXTENSIONS.get(base) or mimetypes.guess_extension(base) or ".bin"


@lru_cache
def get_client() -> Minio:
    settings = get_settings()
    endpoint = urlparse(settings.s3_endpoint)
    return Minio(
        endpoint.netloc,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=endpoint.scheme == "https",
    )


def ensure_bucket() -> None:
    """Create the evidence bucket with Object Lock if missing; fail if an existing one lacks it."""
    global _bucket_ready
    if _bucket_ready:
        return
    client = get_client()
    bucket = get_settings().s3_bucket_evidence
    if not client.bucket_exists(bucket):
        try:
            client.make_bucket(bucket, object_lock=True)
            logger.info("Created evidence bucket %s with Object Lock", bucket)
        except S3Error as exc:
            if exc.code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise
    try:
        client.get_object_lock_config(bucket)
    except S3Error as exc:
        if exc.code == "ObjectLockConfigurationNotFoundError":
            raise RuntimeError(
                f"Bucket {bucket!r} exists without Object Lock; evidence requires a bucket created with it"
            ) from exc
        raise
    _bucket_ready = True


def request_timestamp(digest: bytes, tsa_url: str) -> bytes | None:
    """RFC 3161 timestamp token (DER) for a sha256 digest, or None on any failure.

    Only the digest leaves the system. A TSA failure never fails the capture.
    """
    nonce = secrets.randbits(63)
    message_imprint = tsp.MessageImprint(
        {"hash_algorithm": algos.DigestAlgorithm({"algorithm": "sha256"}), "hashed_message": digest}
    )
    request = tsp.TimeStampReq({"version": "v1", "message_imprint": message_imprint, "nonce": nonce, "cert_req": True})
    try:
        response = httpx.post(
            tsa_url,
            content=request.dump(),
            headers={"Content-Type": "application/timestamp-query"},
            timeout=TSA_TIMEOUT_S,
        )
        response.raise_for_status()
        parsed = tsp.TimeStampResp.load(response.content)
        if parsed["status"]["status"].native not in {"granted", "granted_with_mods"}:
            raise ValueError(f"TSA refused the request: {parsed['status']['status'].native}")
        token = parsed["time_stamp_token"]
        info = token["content"]["encap_content_info"]["content"].parsed
        if info["message_imprint"]["hashed_message"].native != digest or info["nonce"].native != nonce:
            raise ValueError("TSA response does not match the request")
        return bytes(token.dump())
    except Exception:
        logger.exception("RFC 3161 timestamp failed; continuing without a token")
        return None


def put_evidence(
    session: Session,
    data: bytes,
    kind: EvidenceKind,
    content_type: str,
    source_url: str | None = None,
    *,
    link: EvidenceLink,
    created_by: int | None = None,
    captured_at: datetime | None = None,
) -> Evidence:
    """Record the Evidence row (flushed, not committed) and store the bytes under Object Lock.

    `captured_at` dates a capture made earlier than now (demo data); such evidence gets no RFC 3161 token, since a
    token states the time it was issued.

    The row is flushed first so constraint violations surface before anything is written to the
    locked bucket; if the upload then fails the caller's transaction is rolled back. If the commit
    fails after a successful upload, a locked orphan object remains (never a row without an object).
    """
    settings = get_settings()
    owner_name, owner_id = link.owner()
    ensure_bucket()

    digest = hashlib.sha256(data)
    retention_until = datetime.now(UTC) + timedelta(days=settings.evidence_retention_days)
    lock_mode = LockMode(settings.evidence_lock_mode)
    key = f"{owner_name.removesuffix('_id')}/{owner_id}/{secrets.token_hex(16)}{extension_for(content_type)}"
    timestamped = settings.tsa_url and captured_at is None
    tsa_token = request_timestamp(digest.digest(), settings.tsa_url) if timestamped else None

    evidence = Evidence(
        kind=kind,
        bucket=settings.s3_bucket_evidence,
        s3_key=key,
        sha256=digest.hexdigest(),
        size_bytes=len(data),
        content_type=content_type,
        source_url=source_url,
        retention_until=retention_until,
        lock_mode=lock_mode,
        tsa_token=tsa_token,
        created_by=created_by,
        **vars(link),
    )
    if captured_at is not None:
        evidence.captured_at = captured_at
    session.add(evidence)
    session.flush()
    session.refresh(evidence)

    get_client().put_object(
        settings.s3_bucket_evidence,
        key,
        io.BytesIO(data),
        len(data),
        content_type=content_type,
        retention=Retention(lock_mode.value, retention_until),
    )
    return evidence


def open_evidence(evidence: Evidence) -> BaseHTTPResponse:
    """Open the stored object. Raises S3Error if it is missing."""
    return get_client().get_object(evidence.bucket, evidence.s3_key)


def stream_object(response: BaseHTTPResponse) -> Iterator[bytes]:
    try:
        yield from response.stream(STREAM_CHUNK_BYTES)
    finally:
        response.close()
        response.release_conn()

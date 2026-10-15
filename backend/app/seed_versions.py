"""Demo publication that was edited and then deleted at its source (SPEC 10.6), loaded with `--demo`.

`seed_data/demo_versions.json` holds a fictional object with one ad: the saved original, a later version and the
moment its removal was found. Kept apart from demo_objects.json, so the scenarios of the case stay as they are.
"""

import hashlib
import io
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Self

from minio.retention import Retention
from pydantic import ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.config import get_settings
from app.models import AdPost, ConstructionObject, Developer, Evidence
from app.models.enums import AdOrigin, AdVersionSource, CaptureStatus, EvidenceKind, LockMode
from app.modules.ads.versions import record_version
from app.phones import normalize_phone
from app.seed import SEED_DATA_DIR, DemoDeveloper, DemoObject, RelativeDateTime, _add_demo_object, _Strict

logger = logging.getLogger("app.seed")

FILE_NAME = "demo_versions.json"


class DemoVersion(_Strict):
    observed_after_hours: float
    source: AdVersionSource
    text: str
    # File in seed_data with the screenshot that showed this text.
    screenshot: str | None = None


class DemoHistory(_Strict):
    # When the original was captured; later moments are given in hours after it.
    captured: RelativeDateTime
    original_screenshot: str
    versions: list[DemoVersion]
    removed_after_hours: float


class DemoVersions(_Strict):
    developers: list[DemoDeveloper]
    object: DemoObject
    history: DemoHistory

    @model_validator(mode="after")
    def _one_ad(self) -> Self:
        if len(self.object.ads) != 1:
            raise ValueError("the object must have exactly one ad")
        return self


def _store_screenshot(session: Session, ad: AdPost, file_name: str, captured_at: datetime) -> Evidence:
    """Put a screenshot file of seed_data into the evidence storage, dated like the capture it stands for.

    A real capture goes through `storage.put_evidence`, which stamps the time of storing; this one was "taken"
    days ago. For the same reason it has no RFC 3161 token: a token states when it was issued.
    """
    settings = get_settings()
    data = (SEED_DATA_DIR / file_name).read_bytes()
    storage.ensure_bucket()
    key = f"ad_post/{ad.id}/{secrets.token_hex(16)}.png"
    retention_until = datetime.now(UTC) + timedelta(days=settings.evidence_retention_days)
    lock_mode = LockMode(settings.evidence_lock_mode)
    evidence = Evidence(
        kind=EvidenceKind.screenshot_png,
        bucket=settings.s3_bucket_evidence,
        s3_key=key,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        content_type="image/png",
        captured_at=captured_at,
        source_url=ad.url,
        retention_until=retention_until,
        lock_mode=lock_mode,
        ad_post_id=ad.id,
    )
    session.add(evidence)
    session.flush()
    storage.get_client().put_object(
        settings.s3_bucket_evidence,
        key,
        io.BytesIO(data),
        len(data),
        content_type="image/png",
        retention=Retention(lock_mode.value, retention_until),
    )
    return evidence


def seed_demo_versions(session: Session) -> list[int]:
    """Create the edited and deleted demo publication with its object; returns the new object ids (none when it
    exists). Flushed, not committed."""
    path = SEED_DATA_DIR / FILE_NAME
    if not path.exists():
        logger.warning("%s not found: no demo publication with versions loaded", path)
        return []
    try:
        data = DemoVersions.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise SystemExit(f"{FILE_NAME} is invalid:\n{exc}") from exc
    if session.scalar(
        select(ConstructionObject.id).where(
            ConstructionObject.is_demo.is_(True), ConstructionObject.name == data.object.name
        )
    ):
        return []

    for developer in data.developers:
        if session.scalar(select(Developer.id).where(Developer.bin == developer.bin)) is None:
            payload = developer.model_dump()
            payload["phones"] = [phone for raw in developer.phones if (phone := normalize_phone(raw))]
            session.add(Developer(**payload))
    session.flush()

    object_id = _add_demo_object(session, data.object)
    ad = session.scalars(select(AdPost).where(AdPost.object_id == object_id)).one()
    history = data.history
    removed_at = history.captured + timedelta(hours=history.removed_after_hours)
    ad.origin = AdOrigin.capture
    ad.capture_status = CaptureStatus.done
    ad.captured_at = history.captured
    ad.last_checked_at = removed_at
    ad.removed_detected_at = removed_at
    _store_screenshot(session, ad, history.original_screenshot, history.captured)
    for item in history.versions:
        observed_at = history.captured + timedelta(hours=item.observed_after_hours)
        screenshot = _store_screenshot(session, ad, item.screenshot, observed_at) if item.screenshot else None
        version = record_version(
            session, ad, item.text, item.source, observed_at, screenshot.id if screenshot else None
        )
        if version is None:
            raise SystemExit(f"{FILE_NAME}: a version must differ from the saved text of the ad")
    return [object_id]

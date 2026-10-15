"""Builders for the risk, signals and dashboard tests (not a test module: nothing here is collected)."""

import io
from datetime import UTC, date, datetime

from PIL import Image
from sqlalchemy.orm import Session

from app.models import (
    AdPost,
    Complaint,
    ConstructionObject,
    Document,
    Inspection,
    PhraseHit,
    Territory,
)
from app.models.enums import (
    CheckStatus,
    ComplaintStatus,
    DetectedBy,
    DocType,
    PhraseCategory,
    Platform,
)
from tests.conftest import make_object

# A fixed "now" (Tuesday, 07:00 in Almaty) keeps time-dependent rules deterministic.
NOW = datetime(2026, 10, 13, 2, 0, tzinfo=UTC)
TODAY = date(2026, 10, 13)

_counter = {"ad": 0}


def add_document(
    db: Session, obj: ConstructionObject, doc_type: DocType, status: CheckStatus = CheckStatus.confirmed
) -> Document:
    document = Document(object_id=obj.id, doc_type=doc_type, check_status=status)
    db.add(document)
    db.flush()
    return document


def add_ad(
    db: Session,
    obj: ConstructionObject,
    published_at: datetime = NOW,
    *,
    hits: tuple[tuple[PhraseCategory, DetectedBy, bool | None], ...] = (),
    payment_schemes: tuple[str, ...] = (),
    price_before_completion: bool = False,
) -> AdPost:
    _counter["ad"] += 1
    ad = AdPost(
        platform=Platform.instagram,
        external_id=f"test-{_counter['ad']}-{obj.id}",
        url=f"https://example.kz/p/{_counter['ad']}",
        text="Бронь квартир",
        object_id=obj.id,
        published_at=published_at,
        captured_at=published_at,
        payment_schemes=list(payment_schemes),
        price_before_completion=price_before_completion,
    )
    db.add(ad)
    db.flush()
    for category, detected_by, confirmed in hits:
        db.add(
            PhraseHit(
                ad_post_id=ad.id,
                category=category,
                matched_text="бронь",
                start=0,
                end=5,
                weight=10,
                detected_by=detected_by,
                confirmed=confirmed,
            )
        )
    db.flush()
    return ad


def add_complaint(
    db: Session,
    obj: ConstructionObject,
    *,
    collective: bool = False,
    status: ComplaintStatus = ComplaintStatus.new,
    confirmed_payments: bool = False,
    external_id: str | None = None,
) -> Complaint:
    complaint = Complaint(
        object_id=obj.id,
        received_at=TODAY,
        is_collective=collective,
        status=status,
        confirmed_payments=confirmed_payments,
        external_id=external_id,
    )
    db.add(complaint)
    db.flush()
    return complaint


def add_inspection(db: Session, obj: ConstructionObject, inspected_at: date = TODAY, pct: int = 50) -> Inspection:
    inspection = Inspection(object_id=obj.id, inspected_at=inspected_at, readiness_pct=pct)
    db.add(inspection)
    db.flush()
    return inspection


def red_object(db: Session, territory: Territory, name: str = "ЖК Красный") -> ConstructionObject:
    """An object that scores red: no permit and a dictionary booking phrase in a fresh ad."""
    obj = make_object(db, territory, name)
    add_ad(db, obj, hits=((PhraseCategory.booking, DetectedBy.dictionary, None),))
    return obj


def png_bytes(width: int = 320, height: int = 200, color: str = "#2255aa") -> bytes:
    """A real, decodable PNG (WeasyPrint rejects the stub bytes other tests use)."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()

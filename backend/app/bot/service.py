"""Business logic of the citizen bot over a SQLAlchemy session. The Telegram handlers only translate updates."""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz, utils
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.events import object_changed
from app.models import AdPost, Complaint, ConstructionObject, Developer, Document, Territory
from app.models.enums import (
    AdOrigin,
    CaptureStatus,
    CheckSource,
    ComplaintSource,
    ComplaintStatus,
    ConstructionStatus,
    DocType,
    EvidenceKind,
    NotificationKind,
    OcrStatus,
    Platform,
    Role,
    TerritoryLevel,
)
from app.modules.ads import service as ads_service
from app.modules.ads.urls import detect_platform, is_http_url
from app.modules.nlp.service import GENERIC_NAME_WORDS
from app.modules.nlp.text import extract_links, strip_ocr_marker
from app.modules.objects.service import territory_today
from app.modules.risk import engine
from app.modules.signals.notifications import add_notifications, users_covering_territory
from app.storage import EvidenceLink
from app.uploads import PHOTO_TYPES, sniff_content_type

logger = logging.getLogger(__name__)

TEXT_MAX_CHARS = 4000
URL_MAX_CHARS = 2000  # the length of `ad_post.url`
PHOTO_LIMIT = 10
PHOTO_MAX_BYTES = 10 * 1024 * 1024
MAX_MATCHES = 3
# token_set_ratio (0..100) below which an object is not offered for a typed name.
MIN_MATCH_SCORE = 70
MIN_QUERY_CHARS = 2
MAX_QUERY_CHARS = 100

REPORT_NOTICE = "Сообщение гражданина: реклама"


class EmptyReportError(Exception):
    """The citizen's message has no text, no link and no usable photo."""


@dataclass(frozen=True)
class City:
    id: int
    name: str


@dataclass(frozen=True)
class ObjectMatch:
    id: int
    name: str


@dataclass(frozen=True)
class ReportResult:
    ad_id: int
    photos_saved: int


@dataclass(frozen=True)
class LegalCheck:
    """The state of one document that gives a legal basis for attracting the money of share-holders."""

    doc_type: DocType
    status: str  # confirmed, checking, not_found or none (no record), as the risk module reads the checks
    checked_on: date | None
    source: CheckSource | None


@dataclass(frozen=True)
class ObjectFacts:
    """What the bot may tell about a complex. Nothing here comes from the risk assessment."""

    name: str
    developer_name: str | None
    developer_bin: str | None
    stage: ConstructionStatus
    checks: list[LegalCheck]
    is_demo: bool


# ---------------------------------------------------------------- cities and search


def list_cities(session: Session) -> list[City]:
    rows = session.execute(
        select(Territory.id, Territory.name).where(Territory.level == TerritoryLevel.city).order_by(Territory.name)
    )
    return [City(row.id, row.name) for row in rows]


def find_city(session: Session, territory_id: int) -> City | None:
    row = session.execute(
        select(Territory.id, Territory.name).where(Territory.id == territory_id, Territory.level == TerritoryLevel.city)
    ).first()
    return City(row.id, row.name) if row else None


def _normalized(name: str) -> str:
    """Lower case, no punctuation, `ё` as `е` and without the words every complex has («ЖК», «комплекс»)."""
    words = str(utils.default_process(name.replace("ё", "е").replace("Ё", "Е"))).split()
    return " ".join(word for word in words if word not in GENERIC_NAME_WORDS)


def search_objects(session: Session, territory_id: int, query: str) -> list[ObjectMatch]:
    """Up to `MAX_MATCHES` objects of the city whose name or alias is close to the typed name, best first."""
    wanted = _normalized(query[:MAX_QUERY_CHARS])
    if len(wanted) < MIN_QUERY_CHARS:
        return []
    rows = session.execute(
        select(ConstructionObject.id, ConstructionObject.name, ConstructionObject.aliases).where(
            ConstructionObject.territory_id == territory_id
        )
    )
    scored = [
        (max(fuzz.token_set_ratio(wanted, _normalized(name)) for name in (row.name, *row.aliases)), row) for row in rows
    ]
    best = sorted(
        ((score, row) for score, row in scored if score >= MIN_MATCH_SCORE),
        key=lambda item: (-item[0], item[1].name, item[1].id),
    )
    return [ObjectMatch(row.id, row.name) for _, row in best[:MAX_MATCHES]]


def object_name(session: Session, territory_id: int, object_id: int) -> str | None:
    """The name of the object when it belongs to the city (a button of another chat is not trusted)."""
    return session.scalar(
        select(ConstructionObject.name).where(
            ConstructionObject.id == object_id, ConstructionObject.territory_id == territory_id
        )
    )


# ---------------------------------------------------------------- report of advertising


def forwarded_post_url(channel_username: str | None, message_id: int) -> str | None:
    """Link to a post forwarded from a public channel; a channel without a username has no public link."""
    return f"https://t.me/{channel_username}/{message_id}" if channel_username else None


# The link of a citizen is opened by the browser of the capture worker, so only the public platforms the project
# watches are opened. A link to any other site stays in the text of the report.
CAPTURED_PLATFORMS = frozenset({Platform.instagram, Platform.tiktok, Platform.telegram, Platform.aggregator})


def find_report_url(text: str, entity_urls: Iterable[str], forwarded_url: str | None) -> str | None:
    """The publication to capture: the forwarded post, else the first link of the entities or the text that points
    to a captured platform."""
    if forwarded_url is not None:
        return forwarded_url
    for candidate in (*entity_urls, *extract_links(text)):
        # Telegram marks `t.me/x` and `www.x.kz` as links too, without a scheme.
        url = candidate if candidate.lower().startswith(("http://", "https://")) else f"https://{candidate}"
        if is_http_url(url) and len(url) <= URL_MAX_CHARS and detect_platform(url) in CAPTURED_PLATFORMS:
            return url
    return None


def _usable_photos(photos: Sequence[bytes]) -> list[tuple[bytes, str]]:
    usable: list[tuple[bytes, str]] = []
    for data in photos:
        content_type = sniff_content_type(data) if 0 < len(data) <= PHOTO_MAX_BYTES else None
        if content_type is None or content_type not in PHOTO_TYPES:
            logger.warning("A photo of a citizen report is skipped: not a JPEG, PNG or WebP image of up to 10 MB")
            continue
        usable.append((data, content_type))
        if len(usable) == PHOTO_LIMIT:
            break
    return usable


def submit_citizen_report(
    session: Session, *, territory_id: int, text: str, url: str | None, photos: Sequence[bytes]
) -> ReportResult:
    """Store the report as a publication of origin `citizen`, tell the officers of the city and queue the pipeline.

    The citizen is not identified: no author, no Telegram id. Raises `EmptyReportError` when there is nothing to store.
    """
    text = strip_ocr_marker(text.strip())[:TEXT_MAX_CHARS]
    usable = _usable_photos(photos)
    if not (text or url or usable):
        raise EmptyReportError
    ad = AdPost(
        territory_id=territory_id,
        platform=detect_platform(url) if url else Platform.other,
        url=url,
        external_id=f"citizen-{uuid4().hex}",
        author=None,
        text=text,
        # With a link the capture worker sets the time; without one the received message is the capture.
        captured_at=None if url else datetime.now(UTC),
        capture_status=CaptureStatus.pending if url else None,
        origin=AdOrigin.citizen,
    )
    session.add(ad)
    session.flush()
    for data, content_type in usable:
        storage.put_evidence(
            session, data, EvidenceKind.photo, content_type, link=EvidenceLink(ad_post_id=ad.id), created_by=None
        )
    if usable:
        ad.ocr_status = OcrStatus.pending
    add_notifications(
        session,
        users_covering_territory(session, territory_id, [Role.mio_officer]),
        NotificationKind.citizen_report,
        "ad_post",
        ad.id,
        {"name": REPORT_NOTICE},
    )
    ad_id = ad.id
    session.commit()
    if not ads_service.dispatch_pipeline(ad_id, capture=url is not None, requested_by=None):
        ads_service.mark_capture_unqueued(session, ad)
    return ReportResult(ad_id=ad_id, photos_saved=len(usable))


# ---------------------------------------------------------------- complaint


def submit_complaint(session: Session, *, object_id: int, text: str) -> str:
    """Register an unverified complaint of one citizen and tell the officers of the city; returns the object name.

    Raises `LookupError` when the object is gone.
    """
    obj = session.get(ConstructionObject, object_id)
    if obj is None:
        raise LookupError(f"construction object {object_id} not found")
    session.add(
        Complaint(
            object_id=obj.id,
            received_at=territory_today(session, obj.territory_id),
            source=ComplaintSource.telegram,
            is_collective=False,
            signatories_count=1,
            summary=text.strip()[:TEXT_MAX_CHARS],
            status=ComplaintStatus.new,
            is_verified=False,
        )
    )
    session.flush()
    add_notifications(
        session,
        users_covering_territory(session, obj.territory_id, [Role.mio_officer]),
        NotificationKind.citizen_report,
        "object",
        obj.id,
        {"object_name": obj.name},
    )
    name = obj.name
    session.commit()
    object_changed(obj.id)
    return name


# ---------------------------------------------------------------- facts


def object_facts(session: Session, territory_id: int, object_id: int) -> ObjectFacts | None:
    """The developer, the stage and the checks of the guarantee and the permit; None if the city has no such object.

    The statuses are read the way the risk module reads them for the legal basis (`engine.document_statuses`); the
    date and the source belong to the latest check with that outcome.
    """
    obj = session.scalar(
        select(ConstructionObject).where(
            ConstructionObject.id == object_id, ConstructionObject.territory_id == territory_id
        )
    )
    if obj is None:
        return None
    developer = session.get(Developer, obj.developer_id) if obj.developer_id is not None else None
    timezone = ZoneInfo(session.scalars(select(Territory.timezone).where(Territory.id == territory_id)).one())
    documents = session.scalars(
        select(Document)
        .where(Document.object_id == obj.id, Document.doc_type.in_(engine.LEGAL_BASIS_DOC_TYPES))
        .order_by(Document.id)
    ).all()
    statuses = engine.document_statuses(
        [engine.DocumentFact(id=doc.id, doc_type=doc.doc_type, check_status=doc.check_status) for doc in documents]
    )
    checks: list[LegalCheck] = []
    for doc_type in engine.LEGAL_BASIS_DOC_TYPES:
        status = statuses[doc_type.value]
        behind_status = [doc for doc in documents if doc.doc_type is doc_type and doc.check_status.value == status]
        latest = max(
            behind_status, key=lambda doc: (doc.checked_at or datetime.min.replace(tzinfo=UTC), doc.id), default=None
        )
        checked_at = latest.checked_at if latest else None
        checks.append(
            LegalCheck(
                doc_type=doc_type,
                status=status,
                checked_on=checked_at.astimezone(timezone).date() if checked_at else None,
                source=latest.check_source if latest else None,
            )
        )
    return ObjectFacts(
        name=obj.name,
        developer_name=developer.name if developer else None,
        developer_bin=developer.bin if developer else None,
        stage=obj.construction_status,
        checks=checks,
        is_demo=obj.is_demo,
    )

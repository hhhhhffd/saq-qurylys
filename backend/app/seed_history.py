"""Dated history of the demo objects (SPEC 10.5): older facts from `seed_data/demo_history.json` and the replay of the
score over the last 26 weeks, so the time machine of the map has something honest to show.

Nothing here writes a score by hand: the facts get their real dates and `replay_history` runs the risk engine over
them. Every fact is older than the analysis window, so the current score of a demo object does not change.
"""

import logging
from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.geo import make_point
from app.models import AdPost, Complaint, ConstructionObject, Document, Phrase
from app.models.enums import DocType, LinkMethod
from app.modules.nlp.service import analyze_ad
from app.modules.risk.replay import replay_history
from app.phones import normalize_phone
from app.seed import SEED_DATA_DIR, DemoAd, DemoComplaint, RelativeDateTime

logger = logging.getLogger("app.seed")

HISTORY_FILE = "demo_history.json"
HISTORY_WEEKS = 26
HISTORY_STEP = timedelta(weeks=1)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentCheckDate(_Strict):
    """The demo object already has this document; it was checked earlier than the demo data say."""

    doc_type: DocType
    checked_at: RelativeDateTime


class ComplaintVerificationDate(_Strict):
    """The demo object already has this complaint; it was verified earlier than the demo data say."""

    external_id: str
    verified_at: RelativeDateTime


class HistoryObject(_Strict):
    name: str
    ads: list[DemoAd] = []
    complaints: list[DemoComplaint] = []
    document_checks: list[DocumentCheckDate] = []
    complaint_verifications: list[ComplaintVerificationDate] = []


class HistoryData(_Strict):
    objects: list[HistoryObject] = []


def _add_facts(session: Session, obj: ConstructionObject, item: HistoryObject, captured_at: datetime) -> None:
    for ad in item.ads:
        if session.scalar(
            select(AdPost.id).where(AdPost.platform == ad.platform, AdPost.external_id == ad.external_id)
        ):
            continue
        session.add(
            AdPost(
                territory_id=obj.territory_id,
                platform=ad.platform,
                url=ad.url,
                external_id=ad.external_id,
                author=ad.author,
                published_at=ad.published_at,
                captured_at=captured_at,
                text=ad.text,
                phones=[phone for raw in ad.phones if (phone := normalize_phone(raw))],
                object_id=obj.id,
                link_confidence=1.0,
                link_method=LinkMethod.manual,
                payment_schemes=[scheme.value for scheme in ad.payment_schemes],
                claimed_readiness_pct=ad.claimed_readiness_pct,
                price_before_completion=ad.price_before_completion,
                is_outdoor=ad.is_outdoor,
                location=make_point(ad.lat, ad.lon),
                status=ad.status,
                is_demo=True,
            )
        )
    for complaint in item.complaints:
        if complaint.external_id and session.scalar(
            select(Complaint.id).where(
                Complaint.source == complaint.source, Complaint.external_id == complaint.external_id
            )
        ):
            continue
        session.add(Complaint(object_id=obj.id, **complaint.model_dump()))
    for check in item.document_checks:
        documents = list(
            session.scalars(select(Document).where(Document.object_id == obj.id, Document.doc_type == check.doc_type))
        )
        if not documents:
            raise SystemExit(f"{HISTORY_FILE}: {obj.name!r} has no {check.doc_type.value} document to date")
        for document in documents:
            document.checked_at = check.checked_at
    for verification in item.complaint_verifications:
        complaint_row = session.scalar(
            select(Complaint).where(Complaint.object_id == obj.id, Complaint.external_id == verification.external_id)
        )
        if complaint_row is None or not complaint_row.is_verified:
            raise SystemExit(f"{HISTORY_FILE}: {obj.name!r} has no verified complaint {verification.external_id!r}")
        complaint_row.verified_at = verification.verified_at


def _replay_range() -> tuple[datetime, datetime]:
    """The last 26 weeks up to this midnight (UTC). Slices on a daily grid: repeating the replay on the same day
    replaces its own rows exactly instead of leaving a second set of slices a few seconds apart."""
    end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return end - HISTORY_WEEKS * HISTORY_STEP, end


def seed_demo_history(session: Session, object_ids: Collection[int]) -> int:
    """Add the history of the demo objects among `object_ids`, then replay their scores. Returns the number of
    stored slices. Safe to repeat: known facts are skipped, the replay replaces its own rows.

    The ads of these objects are analysed here (the dictionary hits are what R2 reads), as the `nlp.analyze` task
    would do a moment later: a replay without hits would not see a single offer of money.
    """
    path = SEED_DATA_DIR / HISTORY_FILE
    if not path.exists():
        logger.warning("%s not found: no demo history loaded", path)
        return 0
    try:
        data = HistoryData.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise SystemExit(f"{HISTORY_FILE} is invalid:\n{exc}") from exc

    objects = {
        obj.name: obj
        for obj in session.scalars(
            select(ConstructionObject)
            .where(ConstructionObject.id.in_(object_ids), ConstructionObject.is_demo.is_(True))
            .order_by(ConstructionObject.id)
        )
    }
    captured_at = datetime.now(UTC)
    for item in data.objects:
        if item.name in objects:
            _add_facts(session, objects[item.name], item, captured_at)
    session.flush()

    phrases = list(session.scalars(select(Phrase).where(Phrase.is_active)))
    for ad in session.scalars(select(AdPost).where(AdPost.object_id.in_([obj.id for obj in objects.values()]))):
        analyze_ad(session, ad, phrases)

    start, end = _replay_range()
    return sum(replay_history(session, obj, start, end, HISTORY_STEP) for obj in objects.values())


def replay_all(session_factory: sessionmaker[Session]) -> int:
    """Replay the last 26 weeks, weekly, for every object in the database (what `--replay-history` runs). Each
    object is committed on its own. Returns the number of stored slices."""
    stored = 0
    start, end = _replay_range()
    with session_factory() as session:
        object_ids = list(session.scalars(select(ConstructionObject.id).order_by(ConstructionObject.id)))
        for object_id in object_ids:
            stored += replay_history(session, session.get_one(ConstructionObject, object_id), start, end, HISTORY_STEP)
            session.commit()
    logger.info("Replayed the score history of %s objects (%s slices)", len(object_ids), stored)
    return stored

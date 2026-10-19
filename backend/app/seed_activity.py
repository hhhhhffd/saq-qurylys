"""The living demo around the demo objects, loaded with `--demo` after the objects themselves.

`seed_data/demo_activity.json` describes what the integrations would have produced if they all were on: sources
(`SourceAccount`) of every platform with the publications "collected" from them, publications sent by citizens and
complaints that came through the Telegram bot, E-Otinish and by hand, inspections with photos, registry check
records, signal cards in every status, assignments and the notifications that follow. Nothing is collected from the
internet: every text, URL (`example.invalid`), phone (`+7 700 000 ...`) and picture is invented.

Where a service function exists it does the work (`submit_complaint`, `submit_citizen_report`, the signal card
transitions, `analyze_ad`, `link_ad`, `recalculate`), so the data has the shape of the real flow, the audit trail and
the notifications included. Every piece is idempotent on its own: a repeated run finds what exists and adds nothing.

Sources are stored with `is_watched=false`. The collectors and the Telegram userbot poll only watched sources
(`SourceAccount.is_watched`), so a demo source is never read, never joined, never gets a `last_error`.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, storage
from app.bot.service import submit_citizen_report, submit_complaint
from app.geo import make_point
from app.models import (
    AdPost,
    AppSetting,
    AppUser,
    Assignment,
    Complaint,
    ConstructionObject,
    Developer,
    Document,
    Evidence,
    Inspection,
    LinkedEntity,
    Notification,
    Phrase,
    PhraseHit,
    SignalCard,
    SourceAccount,
    Territory,
)
from app.models.enums import (
    AdOrigin,
    AdReviewState,
    AdStatus,
    AdVersionSource,
    AssignmentStatus,
    CaptureStatus,
    CheckSource,
    CheckStatus,
    ComplaintSource,
    ComplaintStatus,
    DetectedBy,
    EvidenceKind,
    LinkedEntityKind,
    LinkMethod,
    LlmStatus,
    NotificationKind,
    OcrStatus,
    PaymentScheme,
    PhraseCategory,
    Platform,
    Recipient,
    SignalOrigin,
    SignalStatus,
    Zone,
)
from app.modules.ads.versions import record_version
from app.modules.nlp import llm
from app.modules.nlp.service import _add_llm_hits, analyze_ad, link_ad, recompute_weights, supported_facts
from app.modules.nlp.text import OCR_MARKER
from app.modules.registry_sync.schemas import SyncResult
from app.modules.registry_sync.service import REGION_ID_VKO, save_last_sync
from app.modules.risk.service import notify_red_zone, recalculate
from app.modules.signals import service as signals
from app.modules.signals.notifications import add_notifications
from app.modules.signals.schemas import ProposedMeasure, SchemePayments, SectionsPatch, SignalPatch
from app.seed import CITY_CODE, SEED_DATA_DIR, DemoComplaint, RelativeDate, RelativeDateTime
from app.seed_media import post_screenshot, site_frame, to_jpeg
from app.seed_vision import seed_demo_vision
from app.storage import EvidenceLink

logger = logging.getLogger("app.seed")

ACTIVITY_FILE = "demo_activity.json"
# Publications older than the analysis window (30 days) never touch a score: the demo may confirm their link and hits
# the way staff would have done, while the recent ones wait in the queue.
WINDOW_DAYS = 30
AdRef = tuple[int, int | None]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- the file ------------------------------------------------------------------------------------------------------


class ActFinding(_Strict):
    category: PhraseCategory
    quote: str
    confidence: float


class ActLlm(_Strict):
    findings: list[ActFinding]
    payment_schemes: list[PaymentScheme] = []
    claimed_readiness_pct: int | None = None
    price_before_completion: bool = False
    confidence: float = 0.8


class ActVersion(_Strict):
    after_hours: float
    text: str


class ActTriage(_Strict):
    state: AdReviewState
    note: str | None = None


class ActPost(_Strict):
    external_id: str
    url: str | None = None
    author: str | None = None
    published_at: RelativeDateTime
    text: str
    phones: list[str] = []
    ocr_text: str | None = None
    llm: ActLlm | None = None
    versions: list[ActVersion] = []
    removed_after_hours: float | None = None
    triage: ActTriage | None = None
    hits: Literal["confirm", "reject"] | None = None
    confirm_link: bool = False


class ActFeed(_Strict):
    """Publications made from the pools of the file: the same source, many posts over the weeks and months."""

    count: int
    objects: list[str]
    newest_days: float
    oldest_days: float
    post_url: str
    ordinary_every: int = 4
    kazakh_every: int = 0
    ocr_every: int = 0
    version_every: int = 0
    removed_every: int = 0


class ActSource(_Strict):
    platform: Platform
    handle: str
    url: str | None = None
    object: str | None = None
    developer_bin: str | None = None
    last_collected: RelativeDateTime
    posts: list[ActPost] = []
    feed: ActFeed | None = None


class KazakhText(_Strict):
    text: str
    llm: ActLlm


class ActPools(_Strict):
    risky_ru: list[str]
    ordinary_ru: list[str]
    risky_kk: list[KazakhText]
    ocr: list[str]
    triage_notes: list[str]
    complaints: list[str]
    citizen: list[str]
    inspection_notes: list[str]
    # Generated photos of seed_data: a banner by its recognized text, an inspection by the object name.
    ocr_photos: dict[str, str] = {}
    inspection_photos: dict[str, str] = {}


class ActBotComplaint(_Strict):
    object: str
    text: str
    received_at: RelativeDate
    status: ComplaintStatus = ComplaintStatus.new
    verified: bool = False


class ActComplaint(DemoComplaint):
    object: str


class ActCitizen(_Strict):
    text: str
    received_at: RelativeDateTime
    triage: ActTriage | None = None
    confirm_link: bool = False


class ActAction(_Strict):
    do: Literal["edit", "return", "send", "respond", "close"]
    by: str = "demo_mio"
    text: str | None = None
    measures: list[ProposedMeasure] = []
    recipient: Recipient | None = None
    days_ago: float = 0
    payments: SchemePayments | None = None


class ActSignal(_Strict):
    object: str
    origin: SignalOrigin
    created_days_ago: float = 0
    actions: list[ActAction] = []


class ActAssignment(_Strict):
    object: str
    author: str
    assignee: str
    task: str
    created_at: RelativeDateTime
    due_at: RelativeDate
    status: AssignmentStatus = AssignmentStatus.open
    result: str | None = None


class ActSharedEntity(_Strict):
    kind: LinkedEntityKind
    value: str
    note: str | None = None
    objects: list[str]


class ActivityData(_Strict):
    pools: ActPools
    sources: list[ActSource]
    citizen_reports: list[ActCitizen]
    bot_complaints: list[ActBotComplaint]
    complaints: list[ActComplaint]
    complaints_per_object: int
    # Objects of a story of their own (the deleted post of demo_versions.json): no generated reports about them.
    isolated: list[str]
    signals: list[ActSignal]
    assignments: list[ActAssignment]
    shared_entities: list[ActSharedEntity]


# --- helpers -------------------------------------------------------------------------------------------------------


class _Context:
    def __init__(self, session: Session, data: ActivityData) -> None:
        self.session = session
        self.data = data
        self.now = datetime.now(UTC)
        self.phrases = list(session.scalars(select(Phrase).where(Phrase.is_active)))
        self.users = {user.username: user for user in session.scalars(select(AppUser).where(AppUser.is_active))}
        self.mio = self.users["demo_mio"]
        city = session.scalar(select(Territory).where(Territory.code == CITY_CODE))
        if city is None:
            raise SystemExit("the demo activity needs the city territory: run the reference seed first")
        self.city = city
        self.objects = {
            obj.name: obj for obj in session.scalars(select(ConstructionObject).where(ConstructionObject.is_demo))
        }
        self.phones = {
            entity.object_id: entity.value
            for entity in session.scalars(select(LinkedEntity).where(LinkedEntity.kind == LinkedEntityKind.phone))
            if entity.object_id is not None
        }
        self.new_ads: list[AdRef] = []
        self.touched: set[int] = set()

    def obj(self, name: str) -> ConstructionObject:
        found = self.objects.get(name)
        if found is None:
            raise SystemExit(f"{ACTIVITY_FILE}: unknown demo object {name!r}")
        return found

    def user(self, username: str) -> AppUser:
        found = self.users.get(username)
        if found is None:
            raise SystemExit(f"{ACTIVITY_FILE}: unknown demo user {username!r}")
        return found

    def phone_of(self, obj: ConstructionObject) -> str:
        value = self.phones.get(obj.id, "+77000000000")
        return f"+7 {value[2:5]} {value[5:8]} {value[8:10]} {value[10:12]}"


def _decide_hits(session: Session, ad: AdPost, decision: bool, user: AppUser, when: datetime) -> None:
    for hit in session.scalars(select(PhraseHit).where(PhraseHit.ad_post_id == ad.id)):
        hit.confirmed = decision
        hit.confirmed_by = user.id
    session.flush()
    recompute_weights(session, ad)
    ad.reviewed_at = when


def _extraction(spec: ActLlm) -> llm.Extraction:
    return llm.Extraction.model_validate(spec.model_dump(mode="json"))


def _derived_extraction(session: Session, ad: AdPost, index: int) -> llm.Extraction | None:
    """What the model would say about a post the dictionary already reads: the same wordings, with its own doubts."""
    hits = list(
        session.scalars(
            select(PhraseHit)
            .where(PhraseHit.ad_post_id == ad.id, PhraseHit.detected_by == DetectedBy.dictionary)
            .order_by(PhraseHit.start)
        )
    )[:3]
    if not hits:
        return None
    confidences = [0.93, 0.81, 0.44]
    findings = [
        llm.Finding(category=hit.category, quote=hit.matched_text, confidence=confidences[(index + n) % 3])
        for n, hit in enumerate(hits)
    ]
    categories = {finding.category for finding in findings}
    schemes = [scheme for scheme, cats in llm.SCHEME_CATEGORIES.items() if cats & categories]
    return llm.Extraction(
        findings=findings,
        payment_schemes=schemes,
        price_before_completion=PhraseCategory.price_before_completion in categories,
        confidence=0.86 if index % 4 else 0.42,
    )


def _store_extraction(session: Session, ad: AdPost, extraction: llm.Extraction) -> None:
    ad.llm_extraction = supported_facts(extraction, ad.text or "").to_stored()
    ad.llm_status = LlmStatus.done
    _add_llm_hits(session, ad, extraction)
    session.flush()
    recompute_weights(session, ad)


def _process_post(ctx: _Context, account: SourceAccount, post: ActPost, index: int, auto: bool) -> bool:
    """Create one collected publication the way the pipeline would leave it. False when it already exists."""
    session = ctx.session
    if session.scalar(
        select(AdPost.id).where(AdPost.platform == account.platform, AdPost.external_id == post.external_id)
    ):
        return False
    published = post.published_at
    captured = min(published + timedelta(minutes=25), ctx.now)
    age_days = (ctx.now - published).total_seconds() / 86400
    text = post.text + (f"{OCR_MARKER}{post.ocr_text}" if post.ocr_text else "")
    ad = AdPost(
        territory_id=ctx.city.id,
        source_account_id=account.id,
        platform=account.platform,
        url=post.url,
        external_id=post.external_id,
        author=post.author or account.handle,
        published_at=published,
        captured_at=captured,
        text=text,
        phones=[phone.replace(" ", "") for phone in post.phones],
        origin=AdOrigin.collector,
        is_demo=True,
        capture_status=CaptureStatus.done if post.url else None,
        last_checked_at=min(captured + timedelta(hours=7), ctx.now) if post.url else None,
        ocr_status=OcrStatus.done if post.ocr_text else None,
    )
    if post.removed_after_hours is not None:
        ad.removed_detected_at = min(published + timedelta(hours=post.removed_after_hours), ctx.now)
        ad.last_checked_at = ad.removed_detected_at
    session.add(ad)
    session.flush()
    if post.url:
        storage.put_evidence(
            session,
            post_screenshot(
                index, post.text[:26] if account.platform in (Platform.instagram, Platform.tiktok) else None
            ),
            EvidenceKind.screenshot_png,
            "image/png",
            post.url,
            link=EvidenceLink(ad_post_id=ad.id),
            captured_at=captured,
        )
    if post.ocr_text:
        storage.put_evidence(
            session,
            _photo(ctx.data.pools.ocr_photos.get(post.ocr_text))
            or to_jpeg(site_frame(0.0, post.author or account.handle, post.ocr_text, 0.4), 70),
            EvidenceKind.photo,
            "image/jpeg",
            link=EvidenceLink(ad_post_id=ad.id),
            captured_at=captured,
        )
    analyze_ad(session, ad, ctx.phrases)
    if post.llm is not None:
        _store_extraction(session, ad, _extraction(post.llm))
    elif auto and index % 3 != 2:
        derived = _derived_extraction(session, ad, index)
        if derived is not None:
            _store_extraction(session, ad, derived)
    link_ad(session, ad)
    for version in post.versions:
        record_version(
            session,
            ad,
            version.text,
            AdVersionSource.collector,
            min(published + timedelta(hours=version.after_hours), ctx.now),
        )
    _apply_review(ctx, ad, post, age_days, index, auto)
    session.flush()
    ctx.new_ads.append((ad.id, ad.object_id))
    if ad.object_id is not None:
        ctx.touched.add(ad.object_id)
    return True


def _apply_review(ctx: _Context, ad: AdPost, post: ActPost, age_days: float, index: int, auto: bool) -> None:
    """The decisions of staff: a link and wordings confirmed, a post put aside or dismissed."""
    session = ctx.session
    confirm_link, hits, triage = post.confirm_link, post.hits, post.triage
    if auto and not any((confirm_link, hits, triage)):
        old = age_days > WINDOW_DAYS + 1
        if ad.object_id is not None and old and index % 2 == 0:
            confirm_link, hits = True, "confirm"
            triage = ActTriage(state=AdReviewState.reviewed, note=None)
        elif ad.object_id is not None and index % 5 == 1:
            triage = ActTriage(
                state=AdReviewState.deferred, note=ctx.data.pools.triage_notes[index % len(ctx.data.pools.triage_notes)]
            )
        elif ad.object_id is None and ad.max_phrase_weight == 0 and index % 2 == 0:
            triage = ActTriage(state=AdReviewState.irrelevant, note="Не относится к строящемуся жилью")
    when = min((ad.published_at or ctx.now) + timedelta(days=1, hours=index % 9), ctx.now)
    if confirm_link and ad.object_id is not None:
        ad.link_method = LinkMethod.manual
        ad.link_confidence = 1.0
        ad.status = AdStatus.removed_saved if ad.removed_detected_at else AdStatus.captured
    if hits is not None:
        _decide_hits(session, ad, hits == "confirm", ctx.mio, when)
    if triage is not None:
        ad.review_state = triage.state
        ad.review_note = triage.note
        ad.reviewed_by = ctx.mio.id
        ad.reviewed_at = when


def _feed_posts(ctx: _Context, source: ActSource) -> list[ActPost]:
    feed = source.feed
    if feed is None:
        return []
    pools = ctx.data.pools
    posts: list[ActPost] = []
    for i in range(feed.count):
        obj = ctx.obj(feed.objects[i % len(feed.objects)])
        age = feed.newest_days + (feed.oldest_days - feed.newest_days) * i / max(feed.count - 1, 1)
        published = f"-{round(age * 24 + (i * 7) % 11)}h"
        ordinary = bool(feed.ordinary_every) and i % feed.ordinary_every == 0
        kazakh = bool(feed.kazakh_every) and i % feed.kazakh_every == feed.kazakh_every - 1
        spec: ActLlm | None = None
        if kazakh:
            item = pools.risky_kk[i % len(pools.risky_kk)]
            text, spec = item.text.format(obj=obj.name), item.llm
        elif ordinary:
            text = pools.ordinary_ru[i % len(pools.ordinary_ru)].format(obj=obj.name, phone=ctx.phone_of(obj))
        else:
            text = pools.risky_ru[i % len(pools.risky_ru)].format(obj=obj.name, phone=ctx.phone_of(obj))
        risky = not ordinary
        edited = pools.ordinary_ru[(i + 1) % len(pools.ordinary_ru)].format(obj=obj.name, phone=ctx.phone_of(obj))
        posts.append(
            ActPost(
                external_id=f"demo-{source.handle}-{i + 1:03d}",
                url=feed.post_url.format(n=i + 1),
                published_at=published,
                text=text,
                phones=[ctx.phone_of(obj)] if risky else [],
                ocr_text=pools.ocr[i % len(pools.ocr)] if feed.ocr_every and i % feed.ocr_every == 0 else None,
                llm=spec,
                versions=[ActVersion(after_hours=26 + i % 20, text=edited)]
                if feed.version_every and risky and i % feed.version_every == 0
                else [],
                removed_after_hours=60 + (i % 5) * 12
                if feed.removed_every and risky and age > 6 and i % feed.removed_every == feed.removed_every - 1
                else None,
            )
        )
    return posts


# --- sources and publications --------------------------------------------------------------------------------------


def _seed_sources(ctx: _Context) -> int:
    session = ctx.session
    created = 0
    for source in ctx.data.sources:
        account = session.scalar(
            select(SourceAccount).where(
                SourceAccount.platform == source.platform, SourceAccount.handle == source.handle
            )
        )
        if account is None:
            developer_id = None
            if source.developer_bin:
                developer_id = session.scalar(select(Developer.id).where(Developer.bin == source.developer_bin))
            account = SourceAccount(
                platform=source.platform,
                handle=source.handle,
                url=source.url,
                object_id=ctx.obj(source.object).id if source.object else None,
                developer_id=developer_id,
                territory_id=ctx.city.id,
                is_watched=False,  # demo sources are never polled: see the module docstring
                last_collected_at=source.last_collected,
            )
            session.add(account)
            session.flush()
        posts = [(post, False) for post in source.posts] + [(post, True) for post in _feed_posts(ctx, source)]
        for index, (post, auto) in enumerate(posts):
            if _process_post(ctx, account, post, index, auto):
                created += 1
    return created


def _seed_citizen_reports(ctx: _Context) -> int:
    session = ctx.session
    reports = list(ctx.data.citizen_reports)
    names = sorted(set(ctx.objects) - set(ctx.data.isolated))
    for index, template in enumerate(ctx.data.pools.citizen):
        name = names[(index * 3) % len(names)]
        reports.append(
            ActCitizen(
                text=template.format(obj=name),
                received_at=f"-{(index * 5) % 70 + 1}d",
                confirm_link=index % 3 == 0 and (index * 5) % 70 + 1 > WINDOW_DAYS + 1,
            )
        )
    created = 0
    for index, report in enumerate(reports):
        if session.scalar(select(AdPost.id).where(AdPost.origin == AdOrigin.citizen, AdPost.text == report.text)):
            continue
        result = submit_citizen_report(session, territory_id=ctx.city.id, text=report.text, url=None, photos=[])
        ad = session.get_one(AdPost, result.ad_id)
        ad.is_demo = True
        ad.captured_at = report.received_at
        analyze_ad(session, ad, ctx.phrases)
        link_ad(session, ad)
        post = ActPost(
            external_id=ad.external_id or "",
            published_at=report.received_at,
            text=report.text,
            triage=report.triage,
            confirm_link=report.confirm_link,
            hits="confirm" if report.confirm_link else None,
        )
        _apply_review(ctx, ad, post, (ctx.now - report.received_at).days, index, False)
        session.commit()
        ctx.new_ads.append((ad.id, ad.object_id))
        if ad.object_id is not None:
            ctx.touched.add(ad.object_id)
        created += 1
    return created


# --- complaints, inspections, documents, entities -----------------------------------------------------------------


def _seed_complaints(ctx: _Context) -> int:
    session = ctx.session
    created = 0
    for bot_item in ctx.data.bot_complaints:
        obj = ctx.obj(bot_item.object)
        exists = session.scalar(
            select(Complaint.id).where(
                Complaint.object_id == obj.id,
                Complaint.source == ComplaintSource.telegram,
                Complaint.summary == bot_item.text,
            )
        )
        if exists:
            continue
        submit_complaint(session, object_id=obj.id, text=bot_item.text)
        complaint = session.scalars(
            select(Complaint).where(Complaint.object_id == obj.id, Complaint.summary == bot_item.text)
        ).one()
        complaint.received_at = bot_item.received_at
        complaint.status = bot_item.status
        if bot_item.verified:
            complaint.is_verified = True
            complaint.verified_by = ctx.mio.id
            complaint.verified_at = datetime.combine(bot_item.received_at, datetime.min.time(), UTC) + timedelta(days=2)
        session.commit()
        created += 1
    explicit = [(ctx.obj(item.object), item) for item in ctx.data.complaints]
    names = sorted(set(ctx.objects) - set(ctx.data.isolated))
    pool = ctx.data.pools.complaints
    sources = (ComplaintSource.eotinish, ComplaintSource.manual, ComplaintSource.other)
    statuses = (ComplaintStatus.closed, ComplaintStatus.in_review, ComplaintStatus.new, ComplaintStatus.closed)
    for round_no in range(ctx.data.complaints_per_object):
        for position, name in enumerate(names):
            n = round_no * len(names) + position
            days = 4 + (n * 11) % 150
            source = sources[n % len(sources)]
            explicit.append(
                (
                    ctx.obj(name),
                    ActComplaint(
                        object=name,
                        received_at=f"-{days}d",
                        source=source,
                        external_id=f"EO-G{n + 1:03d}" if source is ComplaintSource.eotinish else None,
                        summary=pool[n % len(pool)],
                        status=statuses[n % len(statuses)],
                        is_verified=n % 4 == 0,
                        confirmed_payments=n % 9 == 0,
                    ),
                )
            )
    for obj, item in explicit:
        if item.external_id and session.scalar(
            select(Complaint.id).where(Complaint.source == item.source, Complaint.external_id == item.external_id)
        ):
            continue
        if not item.external_id and session.scalar(
            select(Complaint.id).where(
                Complaint.object_id == obj.id, Complaint.source == item.source, Complaint.summary == item.summary
            )
        ):
            continue
        fields = item.model_dump(exclude={"object"})
        verified_at = (
            datetime.combine(item.received_at, datetime.min.time(), UTC) + timedelta(days=2)
            if item.is_verified
            else None
        )
        session.add(
            Complaint(
                object_id=obj.id,
                verified_by=ctx.mio.id if item.is_verified else None,
                verified_at=verified_at,
                **fields,
            )
        )
        ctx.touched.add(obj.id)
        created += 1
    session.flush()
    return created


def _photo(file_name: str | None) -> bytes | None:
    return (SEED_DATA_DIR / file_name).read_bytes() if file_name else None


def _seed_inspections(ctx: _Context) -> int:
    """Two earlier inspections per object (readiness grows with time) with a photo each. They are older than the
    inspection the object already has, so its current readiness, and with it every score, stays as it was."""
    session = ctx.session
    notes = ctx.data.pools.inspection_notes
    created = 0
    for position, obj in enumerate(sorted(ctx.objects.values(), key=lambda o: o.name)):
        latest = session.scalars(
            select(Inspection).where(Inspection.object_id == obj.id).order_by(Inspection.inspected_at.desc()).limit(1)
        ).first()
        if latest is None:
            continue
        for step, (gap, share) in enumerate(((45, 0.62), (105, 0.3))):
            when = latest.inspected_at - timedelta(days=gap)
            if session.scalar(
                select(Inspection.id).where(Inspection.object_id == obj.id, Inspection.inspected_at == when)
            ):
                continue
            readiness = max(1, round(latest.readiness_pct * share))
            inspection = Inspection(
                object_id=obj.id,
                inspected_at=when,
                readiness_pct=readiness,
                location=make_point(obj.lat, obj.lon),
                inspector_id=ctx.mio.id,
                note=notes[(position + step) % len(notes)],
            )
            session.add(inspection)
            session.flush()
            storage.put_evidence(
                session,
                _photo(ctx.data.pools.inspection_photos.get(obj.name))
                or to_jpeg(site_frame(position + step * 3.0, obj.name, "Фото с выезда", readiness / 100), 70),
                EvidenceKind.photo,
                "image/jpeg",
                link=EvidenceLink(inspection_id=inspection.id),
                created_by=ctx.mio.id,
                captured_at=datetime.combine(when, datetime.min.time(), UTC) + timedelta(hours=11),
            )
            created += 1
    return created


def _seed_registry(ctx: _Context) -> int:
    """A finished sync of the housing portal registry: the raw answer kept as evidence of the checks it confirmed."""
    session = ctx.session
    documents = session.scalars(
        select(Document)
        .join(ConstructionObject, ConstructionObject.id == Document.object_id)
        .where(
            ConstructionObject.is_demo,
            Document.check_source == CheckSource.housing_portal,
            Document.check_status == CheckStatus.confirmed,
        )
    ).all()
    stored = 0
    for document in documents:
        if session.scalar(select(Evidence.id).where(Evidence.document_id == document.id)):
            continue
        raw = json.dumps(
            {"number": document.number, "status": "Действует", "source": "registry.example.invalid"},
            ensure_ascii=False,
        ).encode()
        storage.put_evidence(
            session,
            raw,
            EvidenceKind.registry_response,
            "application/json",
            f"https://registry.example.invalid/objects/{document.id}",
            link=EvidenceLink(document_id=document.id),
            captured_at=document.checked_at or ctx.now,
        )
        stored += 1
    if session.get(AppSetting, "homeportal_last_sync") is None:
        started = ctx.now - timedelta(hours=7)
        save_last_sync(
            session,
            SyncResult(
                ok=True,
                region_id=REGION_ID_VKO,
                started_at=started,
                finished_at=started + timedelta(minutes=4),
                fetched=len(documents) + 3,
                objects_created=0,
                documents_created=0,
                documents_updated=len(documents),
                skipped=3,
            ),
        )
    return stored


def _seed_entities(ctx: _Context) -> int:
    """Websites and sales offices of the objects, the advertising accounts of the demo sources and the details shared
    by two developers: the link graph gets edges that were not in the base demo."""
    session = ctx.session
    created = 0

    def add(object_id: int, kind: LinkedEntityKind, value: str, note: str | None) -> None:
        nonlocal created
        if session.scalar(
            select(LinkedEntity.id).where(
                LinkedEntity.object_id == object_id, LinkedEntity.kind == kind, LinkedEntity.value == value
            )
        ):
            return
        session.add(LinkedEntity(object_id=object_id, kind=kind, value=value, note=note))
        created += 1

    for position, obj in enumerate(sorted(ctx.objects.values(), key=lambda o: o.name)):
        add(obj.id, LinkedEntityKind.website, f"https://zhk-{position + 1:02d}.example.invalid", "Сайт объекта")
        add(obj.id, LinkedEntityKind.sales_office, f"Офис продаж на объекте, {obj.address or 'адрес уточняется'}", None)
    for source in ctx.data.sources:
        if source.object and source.url and source.platform in (Platform.instagram, Platform.telegram, Platform.tiktok):
            add(ctx.obj(source.object).id, LinkedEntityKind.ad_account, source.url, "Рекламный аккаунт застройщика")
    for entity in ctx.data.shared_entities:
        for name in entity.objects:
            add(ctx.obj(name).id, entity.kind, entity.value, entity.note)
    session.flush()
    return created


# --- signal cards and assignments ----------------------------------------------------------------------------------


def _view(session: Session, card: SignalCard) -> signals.CardView:
    obj = session.get_one(ConstructionObject, card.object_id)
    timezone = session.scalars(select(Territory.timezone).where(Territory.id == obj.territory_id)).one()
    return signals.CardView(card=card, object_name=obj.name, zone=obj.zone, timezone=timezone, is_demo=obj.is_demo)


def _run_action(ctx: _Context, card: SignalCard, action: ActAction) -> None:
    session = ctx.session
    user = ctx.user(action.by)
    when = ctx.now - timedelta(days=action.days_ago)
    view = _view(session, card)
    if action.do == "edit":
        sections = SectionsPatch(
            note=action.text, proposed_measures=action.measures or None, scheme_payments=action.payments
        )
        signals.update_card(session, card, SignalPatch(sections=sections), user, None)
    elif action.do == "return":
        signals.return_card(session, view, user, action.text or "Дополните карточку", None)
    elif action.do == "send":
        if action.recipient is None:
            raise SystemExit(f"{ACTIVITY_FILE}: a send action needs a recipient")
        signals.confirm_and_send(session, view, user, action.recipient, None, now=when)
    elif action.do == "respond":
        signals.respond(session, view, user, action.text or "Принято к рассмотрению", None, now=when)
    else:
        signals.close_card(session, view, user, None)


def _seed_signals(ctx: _Context) -> int:
    session = ctx.session
    touched = 0
    for item in ctx.data.signals:
        obj = ctx.obj(item.object)
        cards = list(session.scalars(select(SignalCard).where(SignalCard.object_id == obj.id)))
        if item.origin is SignalOrigin.auto:
            card = next((c for c in cards if c.origin is SignalOrigin.auto), None)
            if card is None:
                if obj.zone is not Zone.red:
                    raise SystemExit(f"{ACTIVITY_FILE}: {obj.name!r} is not red: no automatic card to work with")
                card = signals.create_card(session, obj, SignalOrigin.auto, None)
            if card.status is not SignalStatus.requires_confirmation:
                continue
        else:
            if any(c.origin is SignalOrigin.manual for c in cards):
                continue
            card = signals.create_card(session, obj, SignalOrigin.manual, ctx.mio, None)
            card.created_at = ctx.now - timedelta(days=item.created_days_ago)
        for action in item.actions:
            _run_action(ctx, card, action)
        touched += 1
    session.flush()
    signals.check_deadlines(session)
    return touched


def _seed_assignments(ctx: _Context) -> int:
    session = ctx.session
    created = 0
    for item in ctx.data.assignments:
        obj = ctx.obj(item.object)
        if session.scalar(select(Assignment.id).where(Assignment.object_id == obj.id, Assignment.task == item.task)):
            continue
        author, assignee = ctx.user(item.author), ctx.user(item.assignee)
        assignment = Assignment(
            object_id=obj.id,
            author_id=author.id,
            assignee_id=assignee.id,
            task=item.task,
            due_date=item.due_at,
            status=item.status,
            result=item.result,
            completed_at=min(item.created_at + timedelta(days=3), ctx.now)
            if item.status is AssignmentStatus.done
            else None,
            created_at=item.created_at,
        )
        session.add(assignment)
        session.flush()
        session.refresh(assignment)
        audit.record(
            session, author, "assignment.create", "assignment", assignment.id, None, audit.snapshot(assignment)
        )
        if item.status is AssignmentStatus.open:
            add_notifications(
                session,
                [assignee],
                NotificationKind.assignment_new,
                "construction_object",
                obj.id,
                {"assignment_id": assignment.id, "object_name": obj.name, "due_date": item.due_at.isoformat()},
            )
        created += 1
    return created


# --- entry point ---------------------------------------------------------------------------------------------------


def _recalculate_new(ctx: _Context) -> None:
    """Score what the new facts changed right now, so signal cards are built from real scores and the red objects
    get their automatic drafts (the celery tasks queued later find the objects already red and add nothing)."""
    session = ctx.session
    stale = set(
        session.scalars(
            select(ConstructionObject.id).where(ConstructionObject.is_demo, ConstructionObject.last_scored_at.is_(None))
        )
    )
    for object_id in sorted(stale | ctx.touched):
        result = recalculate(session, object_id)
        if result is not None and result.entered_red:
            notify_red_zone(session, object_id)
    session.flush()


def _mark_read(ctx: _Context, first_new_notification: int) -> None:
    """Most of the old notifications were read by now; the freshest ones stay unread."""
    session = ctx.session
    users = session.scalars(select(AppUser.id).where(AppUser.username.like("demo_%"))).all()
    for user_id in users:
        ids = list(
            session.scalars(
                select(Notification.id)
                .where(Notification.user_id == user_id, Notification.id >= first_new_notification)
                .order_by(Notification.id)
            )
        )
        for notification_id in ids[: len(ids) * 2 // 5]:
            session.get_one(Notification, notification_id).read_at = ctx.now - timedelta(hours=notification_id % 36 + 1)


def seed_demo_activity(session: Session) -> tuple[list[AdRef], set[int]]:
    """Load the file. Returns the new publications (id, object id) that still need the processing chain and the ids of
    the objects whose facts changed. Commits along the way: the bot services commit by themselves."""
    path = SEED_DATA_DIR / ACTIVITY_FILE
    if not path.exists():
        logger.warning("%s not found: no demo activity loaded", path)
        return [], set()
    try:
        data = ActivityData.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise SystemExit(f"{ACTIVITY_FILE} is invalid:\n{exc}") from exc

    ctx = _Context(session, data)
    first_notification = session.scalar(select(func.coalesce(func.max(Notification.id), 0))) or 0
    counts: dict[str, int] = {}
    counts["citizen reports"] = _seed_citizen_reports(ctx)
    counts["complaints"] = _seed_complaints(ctx)
    session.commit()
    counts["publications"] = _seed_sources(ctx)
    for ad_id, object_id in seed_demo_vision(session):
        ctx.new_ads.append((ad_id, object_id))
        if object_id is not None:
            ctx.touched.add(object_id)
    counts["inspections"] = _seed_inspections(ctx)
    counts["registry checks"] = _seed_registry(ctx)
    counts["linked entities"] = _seed_entities(ctx)
    session.flush()
    # Everything the rules read must be analysed before the objects are scored.
    for ad in session.scalars(select(AdPost).where(AdPost.is_demo, AdPost.object_id.is_not(None))):
        analyze_ad(session, ad, ctx.phrases)
    _recalculate_new(ctx)
    counts["signal cards"] = _seed_signals(ctx)
    counts["assignments"] = _seed_assignments(ctx)
    _mark_read(ctx, first_notification + 1)
    session.commit()
    logger.info("Demo activity ready: %s", ", ".join(f"{name} {value}" for name, value in counts.items()))
    # A post with a stored hypothesis of the model must not go through the real model again.
    pending = [
        ref
        for ref in ctx.new_ads
        if ref[1] is not None and session.get_one(AdPost, ref[0]).llm_status is LlmStatus.none
    ]
    return pending, ctx.touched

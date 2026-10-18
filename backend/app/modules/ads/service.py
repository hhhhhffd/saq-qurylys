import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
from celery import chain
from fastapi import Request
from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from app import audit, storage
from app.collectors import default_client
from app.collectors import lock as collect_lock
from app.collectors.base import CollectedPost, CollectorError, get_collector, registered_platforms
from app.collectors.media import download_photos
from app.config import get_settings
from app.errors import api_error
from app.geo import make_point
from app.models import (
    AdPost,
    AdPostVersion,
    AppUser,
    ConstructionObject,
    Evidence,
    PhraseHit,
    SourceAccount,
    VisionFinding,
    VisionFrame,
)
from app.models.enums import (
    AdOrigin,
    AdQueueReason,
    AdReviewState,
    AdStatus,
    AdVersionSource,
    CaptureStatus,
    EvidenceKind,
    NotificationKind,
    OcrStatus,
    Platform,
    Role,
)
from app.modules.ads.schemas import (
    AdDetail,
    AdRow,
    AdVersionOut,
    DuplicateInstance,
    LinkedObject,
    PhraseHitOut,
    VisionSourceOut,
)
from app.modules.ads.urls import handle_from_url
from app.modules.ads.versions import record_version
from app.modules.evidence.schemas import EvidenceOut
from app.modules.nlp.llm import Extraction
from app.modules.nlp.service import finding_for_hit
from app.modules.nlp.text import strip_ocr_marker
from app.modules.settings.service import load_settings
from app.modules.signals.notifications import add_notifications, users_covering_territory
from app.scope import TerritoryScope
from app.storage import EvidenceLink
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)
MAX_DUPLICATE_INSTANCES = 20


def get_ad_in_scope(session: Session, scope: TerritoryScope, ad_id: int, *, for_update: bool = False) -> AdPost:
    """Out-of-scope publications are reported as missing so their existence is not disclosed."""
    stmt = scope.restrict(select(AdPost).where(AdPost.id == ad_id), AdPost.territory_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    ad = session.scalar(stmt)
    if ad is None:
        raise api_error(404, "ad_not_found", "Публикация не найдена")
    return ad


def queue_reasons(ad: AdPost, has_unreviewed_hits: bool) -> list[AdQueueReason]:
    if ad.review_state in {AdReviewState.deferred, AdReviewState.irrelevant}:
        return []
    reasons: list[AdQueueReason] = []
    if ad.capture_status is not None and ad.capture_status.value in {"pending", "failed"}:
        reasons.append(AdQueueReason(f"capture_{ad.capture_status.value}"))
    if ad.ocr_status is not None and ad.ocr_status.value in {"pending", "failed"}:
        reasons.append(AdQueueReason(f"ocr_{ad.ocr_status.value}"))
    if ad.llm_status.value in {"pending", "failed"}:
        reasons.append(AdQueueReason(f"llm_{ad.llm_status.value}"))
    if ad.status is AdStatus.verification:
        reasons.append(AdQueueReason.uncertain_object)
    if has_unreviewed_hits:
        reasons.append(AdQueueReason.unreviewed_phrase_hits)
    if not reasons and ad.review_state is AdReviewState.unreviewed:
        reasons.append(AdQueueReason.manual_review)
    return reasons


def duplicate_metadata(
    session: Session, ads: Sequence[AdPost], scope: TerritoryScope
) -> dict[tuple[int, str], tuple[int, list[DuplicateInstance]]]:
    keys = {(ad.source_account_id, ad.text) for ad in ads if ad.source_account_id is not None and ad.text}
    if not keys:
        return {}

    base = select(
        AdPost.source_account_id.label("source_account_id"),
        AdPost.text.label("text"),
        AdPost.id.label("id"),
        AdPost.url.label("url"),
        AdPost.platform.label("platform"),
        SourceAccount.handle.label("source_label"),
        func.count().over(partition_by=(AdPost.source_account_id, AdPost.text)).label("group_size"),
        func.row_number()
        .over(partition_by=(AdPost.source_account_id, AdPost.text), order_by=AdPost.id)
        .label("instance_rank"),
    ).join(SourceAccount, SourceAccount.id == AdPost.source_account_id)
    base = scope.restrict(base, AdPost.territory_id)
    base = scope.restrict(base, SourceAccount.territory_id).where(
        tuple_(AdPost.source_account_id, AdPost.text).in_(keys)
    )
    grouped = base.subquery()
    rows = session.execute(
        select(grouped)
        .where(grouped.c.group_size > 1, grouped.c.instance_rank <= MAX_DUPLICATE_INSTANCES + 1)
        .order_by(grouped.c.source_account_id, grouped.c.text, grouped.c.id)
    )

    groups: dict[tuple[int, str], tuple[int, list[DuplicateInstance]]] = {}
    for row in rows:
        key = (row.source_account_id, row.text)
        if key not in groups:
            groups[key] = (
                row.group_size - 1,
                [],
            )
        groups[key][1].append(
            DuplicateInstance(id=row.id, url=row.url, platform=row.platform, source_label=row.source_label)
        )
    return groups


def _row_with_metadata(
    ad: AdPost,
    object_name: str | None,
    has_unreviewed_hits: bool,
    duplicates: dict[tuple[int, str], tuple[int, list[DuplicateInstance]]],
) -> AdRow:
    count = 0
    instances: list[DuplicateInstance] = []
    truncated = False
    key = (ad.source_account_id, ad.text) if ad.source_account_id is not None and ad.text else None
    if key is not None and key in duplicates:
        count, group = duplicates[key]
        instances = [item for item in group if item.id != ad.id][:MAX_DUPLICATE_INSTANCES]
        truncated = count > len(instances)
    return AdRow.model_validate(ad).model_copy(
        update={
            "object_name": object_name,
            "queue_reasons": queue_reasons(ad, has_unreviewed_hits),
            "duplicate_count": count,
            "duplicate_instances": instances,
            "duplicate_instances_truncated": truncated,
        }
    )


def build_rows(session: Session, rows: Sequence[tuple[AdPost, str | None]], scope: TerritoryScope) -> list[AdRow]:
    ads = [ad for ad, _ in rows]
    if not ads:
        return []
    ad_ids = [ad.id for ad in ads]
    unreviewed_hit_ad_ids = set(
        session.scalars(
            select(PhraseHit.ad_post_id)
            .where(PhraseHit.ad_post_id.in_(ad_ids), PhraseHit.confirmed.is_(None))
            .distinct()
        )
    )
    duplicates = duplicate_metadata(session, ads, scope)
    return [_row_with_metadata(ad, object_name, ad.id in unreviewed_hit_ad_ids, duplicates) for ad, object_name in rows]


def build_detail(session: Session, ad: AdPost, scope: TerritoryScope) -> AdDetail:
    obj = session.get(ConstructionObject, ad.object_id) if ad.object_id is not None else None
    hits = list(
        session.scalars(select(PhraseHit).where(PhraseHit.ad_post_id == ad.id).order_by(PhraseHit.start, PhraseHit.id))
    )
    evidence = [
        EvidenceOut.model_validate(item)
        for item in session.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id).order_by(Evidence.id))
    ]
    versions = session.scalars(
        select(AdPostVersion)
        .where(AdPostVersion.ad_post_id == ad.id)
        .order_by(AdPostVersion.observed_at, AdPostVersion.id)
    )
    text = ad.text or ""
    extraction = Extraction.model_validate(ad.llm_extraction) if ad.llm_extraction is not None else None
    vision_row = (
        session.execute(
            select(VisionFinding.session_id, VisionFinding.id, VisionFinding.frame_id, VisionFrame.timestamp_ms)
            .outerjoin(VisionFrame, VisionFrame.id == VisionFinding.frame_id)
            .where(VisionFinding.ad_post_id == ad.id)
        ).first()
        if ad.origin is AdOrigin.vision
        else None
    )
    return AdDetail(
        **build_rows(session, [(ad, obj.name if obj else None)], scope)[0].model_dump(),
        phrase_hits=[PhraseHitOut.from_hit(hit, text, finding_for_hit(hit, extraction)) for hit in hits],
        evidence=evidence,
        llm_extraction=extraction,
        linked_object=LinkedObject.model_validate(obj) if obj else None,
        versions=[AdVersionOut.model_validate(version) for version in versions],
        original_captured_at=ad.captured_at or ad.created_at,
        original_evidence=next((item for item in evidence if item.kind is EvidenceKind.screenshot_png), None),
        vision_source=VisionSourceOut(
            session_id=vision_row[0], finding_id=vision_row[1], frame_id=vision_row[2], timestamp_ms=vision_row[3]
        )
        if vision_row is not None
        else None,
    )


def create_manual_ad(
    session: Session,
    user: AppUser,
    request: Request | None,
    *,
    platform: Platform,
    url: str | None,
    external_id: str | None,
    text: str,
    published_at: datetime | None,
    is_outdoor: bool,
    lat: float | None,
    lon: float | None,
    photos: Sequence[tuple[bytes, str]],
    ocr_status: OcrStatus | None,
    fields: dict[str, object],
    origin: AdOrigin = AdOrigin.manual,
    audit_action: str = "ad.manual_create",
) -> AdPost:
    """Create a publication entered by a person, with its photos as evidence. Flushed and audited, not committed.

    `fields` carries the link and territory (see `_new_ad_fields` in the router). The caller validates the input,
    commits, and then calls `dispatch_pipeline`.
    """
    ad = AdPost(
        platform=platform,
        url=url,
        external_id=external_id,
        text=text,
        published_at=published_at,
        captured_at=datetime.now(UTC),
        is_outdoor=is_outdoor,
        location=make_point(lat, lon),
        ocr_status=ocr_status,
        origin=origin,
        **fields,
    )
    session.add(ad)
    session.flush()
    evidence_ids = [
        storage.put_evidence(
            session,
            data,
            EvidenceKind.photo,
            content_type,
            link=EvidenceLink(ad_post_id=ad.id),
            created_by=user.id,
        ).id
        for data, content_type in photos
    ]
    session.refresh(ad)
    audit.record(
        session,
        user,
        audit_action,
        "ad_post",
        ad.id,
        None,
        {**audit.snapshot(ad), "evidence_ids": evidence_ids},
        request,
    )
    return ad


def dispatch_pipeline(ad_post_id: int, *, capture: bool, requested_by: int | None) -> bool:
    """Queue the pipeline of a new publication (SPEC 5, 10.2): capture (when it has a URL), OCR, analyze, link, LLM.

    Call after the post is committed. Returns False when the broker is unreachable; the request whose data is
    already saved must not fail because of it.
    """
    if not get_settings().events_enabled:
        return True
    steps: list[tuple[str, str, list[int | None]]] = [
        ("nlp.ocr", "nlp", [ad_post_id]),
        ("nlp.analyze", "nlp", [ad_post_id]),
        ("nlp.link", "nlp", [ad_post_id]),
        ("nlp.llm_extract", "nlp", [ad_post_id]),
    ]
    if capture:
        steps.insert(0, ("archive.capture", "archive", [ad_post_id, requested_by]))
    try:
        chain(
            *(celery_app.signature(name, args=args, queue=queue, immutable=True) for name, queue, args in steps)
        ).apply_async(retry=False)
    except Exception:
        logger.exception("Failed to enqueue the pipeline of ad_post %s", ad_post_id)
        return False
    return True


def mark_capture_unqueued(session: Session, ad: AdPost) -> None:
    """The pipeline could not be queued, so nothing will end the pending states of the post: show them as failed."""
    if ad.capture_status is CaptureStatus.pending:
        ad.capture_status = CaptureStatus.failed
        ad.capture_error = "Не удалось поставить фиксацию в очередь"
    if ad.ocr_status is OcrStatus.pending:
        ad.ocr_status = OcrStatus.failed
    session.commit()


def refresh_claimed_readiness(session: Session, object_id: int) -> bool:
    """Set the object's claimed readiness to the highest confirmed claim of its ads within the ad window.

    The only writer of `construction_object.readiness_claimed_pct`. Returns whether the value changed.
    """
    obj = session.get(ConstructionObject, object_id)
    if obj is None:
        return False
    window_start = datetime.now(UTC) - timedelta(days=load_settings(session).ad_window_days)
    claimed = session.scalar(
        select(func.max(AdPost.claimed_readiness_pct)).where(
            AdPost.object_id == object_id,
            func.coalesce(AdPost.published_at, AdPost.captured_at, AdPost.created_at) >= window_start,
        )
    )
    if claimed == obj.readiness_claimed_pct:
        return False
    obj.readiness_claimed_pct = claimed
    return True


def refresh_all_claimed_readiness(session: Session) -> list[int]:
    """Refresh the claimed readiness of every object that has or had a claim; returns the changed object ids."""
    with_claims = select(AdPost.object_id).where(AdPost.claimed_readiness_pct.isnot(None), AdPost.object_id.isnot(None))
    object_ids = session.scalars(
        select(ConstructionObject.id).where(
            or_(ConstructionObject.readiness_claimed_pct.isnot(None), ConstructionObject.id.in_(with_claims))
        )
    ).all()
    return [object_id for object_id in object_ids if refresh_claimed_readiness(session, object_id)]


def resolve_source_account(session: Session, platform: Platform, url: str) -> SourceAccount | None:
    """The known account that published the URL, when the platform's URLs carry the handle."""
    handle = handle_from_url(platform, url)
    if handle is None:
        return None
    return session.scalar(
        select(SourceAccount).where(SourceAccount.platform == platform, func.lower(SourceAccount.handle) == handle)
    )


def store_collected_photos(session: Session, ad: AdPost, urls: list[str], client: httpx.Client) -> None:
    """Download the photos of a collected post and keep them as its evidence, then queue them for OCR. Commits.

    The download comes first, while no transaction is open; the evidence is stored in a short one.
    """
    photos = download_photos(client, urls)
    if not photos:
        return
    for photo in photos:
        storage.put_evidence(
            session,
            photo.data,
            EvidenceKind.photo,
            photo.content_type,
            photo.url,
            link=EvidenceLink(ad_post_id=ad.id),
            created_by=None,
        )
    ad.ocr_status = OcrStatus.pending
    session.commit()


def ingest_collected_post(
    session: Session, account: SourceAccount, post: CollectedPost, *, capture: bool
) -> AdPost | None:
    """Store a post found by a collector, without its photos. Flushed, not committed.

    `capture` tells whether the post's URL is opened with the browser. A known post (same platform and external id)
    is not stored again; when its text has changed at the source, the new text is recorded as a version. Returns the
    new post, or None for a known one.
    """
    # Third-party text: PostgreSQL does not store NUL characters, and the OCR marker would pass a part of the text
    # for the recognised one.
    text = strip_ocr_marker(post.text.replace("\x00", ""))
    known = session.scalar(
        select(AdPost).where(AdPost.platform == account.platform, AdPost.external_id == post.external_id)
    )
    if known is not None:
        record_version(session, known, text, AdVersionSource.collector, datetime.now(UTC))
        return None
    territory_id = account.territory_id
    if territory_id is None and account.object_id is not None:
        territory_id = session.scalar(
            select(ConstructionObject.territory_id).where(ConstructionObject.id == account.object_id)
        )
    ad = AdPost(
        territory_id=territory_id,
        source_account_id=account.id,
        platform=account.platform,
        url=post.url,
        external_id=post.external_id,
        author=post.author.replace("\x00", "") if post.author else None,
        published_at=post.published_at,
        text=text,
        links=post.links,
        capture_status=CaptureStatus.pending if capture and post.url else None,
        origin=AdOrigin.collector,
    )
    session.add(ad)
    session.flush()
    return ad


def _notify_collector_failed(session: Session, account: SourceAccount, error: str) -> None:
    """Tell the administrators who cover the account's territory (the national ones for an account without one)."""
    if account.territory_id is None:
        admins: Sequence[AppUser] = session.scalars(
            select(AppUser).where(
                AppUser.role == Role.admin, AppUser.is_active.is_(True), AppUser.territory_id.is_(None)
            )
        ).all()
    else:
        admins = users_covering_territory(session, account.territory_id, {Role.admin})
    payload = {"name": account.handle, "platform": account.platform.value, "error": error}
    add_notifications(session, admins, NotificationKind.collector_failed, "source_account", account.id, payload)


def record_collection_result(session: Session, account: SourceAccount, started_at: datetime, error: str | None) -> None:
    """Record the outcome of a collection on the account; the administrators are told when it starts to fail.
    Not committed."""
    if error is None:
        account.last_collected_at = started_at
        account.last_error = None
        account.last_error_at = None
    else:
        if account.last_error is None:
            _notify_collector_failed(session, account, error)
        account.last_error = error
        account.last_error_at = started_at


def _finish_collected_post(session: Session, ad: AdPost, media_urls: list[str], client: httpx.Client | None) -> None:
    """Store the photos of a committed post and queue its pipeline."""
    ad_id, capture = ad.id, ad.capture_status is CaptureStatus.pending
    if media_urls:
        try:
            store_collected_photos(session, ad, media_urls, client or default_client())
        except Exception:
            # The post is saved; it goes through the pipeline without its photos.
            logger.exception("The photos of ad_post %s were not stored", ad_id)
            session.rollback()
    if not dispatch_pipeline(ad_id, capture=capture, requested_by=None):
        mark_capture_unqueued(session, ad)


def _collect_account(
    session: Session, account: SourceAccount, since: datetime, client: httpx.Client | None
) -> list[int]:
    """Collect one account and record the outcome on it. Commits; returns the ids of the new posts.

    The network is not used inside a transaction (the activity feed reads `created_at`, which is the start of the
    transaction, and an open one holds locks): the posts are read first, then each is stored and committed on its own,
    then its photos are downloaded and stored, and its pipeline is queued.
    """
    collector = get_collector(account.platform)
    if collector is None:
        return []
    # Read before anything can fail: after a failed flush the account is expired until the rollback.
    account_id, platform = account.id, account.platform
    started_at = datetime.now(UTC)

    def is_known(external_id: str) -> bool:
        stmt = select(AdPost.id).where(AdPost.platform == platform, AdPost.external_id == external_id)
        return session.scalar(stmt) is not None

    posts: list[CollectedPost] = []
    created: list[int] = []
    error: str | None = None
    try:
        try:
            posts.extend(collector.collect(account, since, is_known))
        except CollectorError as exc:
            # The posts read before the failure are kept: the source answered for them.
            error = str(exc)
            logger.warning("Collecting source account %s (%s) failed: %s", account_id, platform, error)
        session.commit()  # ends the read transaction before anything is stored
        for post in posts:
            ad = ingest_collected_post(session, account, post, capture=collector.capture_urls)
            session.commit()
            if ad is not None:
                created.append(ad.id)
                _finish_collected_post(session, ad, post.media_urls, client)
    except Exception:
        logger.exception("Collecting source account %s (%s) failed", account_id, platform)
        session.rollback()
        error = "Непредвиденная ошибка сбора, подробности в журнале сервера"
    record_collection_result(session, account, started_at, error)
    session.commit()
    return created


def _collect_accounts(session: Session, accounts: Sequence[SourceAccount], client: httpx.Client | None) -> list[int]:
    default_since = datetime.now(UTC) - timedelta(days=load_settings(session).ad_window_days)
    created: list[int] = []
    for account in accounts:
        collector = get_collector(account.platform)
        if collector is None or not collector.handles(account):
            continue
        account_id = account.id
        try:
            with collect_lock.hold(account_id) as acquired:
                if acquired:
                    created.extend(
                        _collect_account(session, account, account.last_collected_at or default_since, client)
                    )
                else:
                    logger.info("Source account %s is being collected by another run, skipped", account_id)
        except Exception:
            # Whatever went wrong with one account, even while recording it, must not stop the others.
            logger.exception("Collecting source account %s failed", account_id)
            session.rollback()
    return created


def run_collectors(session: Session, client: httpx.Client | None = None) -> list[int]:
    """Collect new posts of the watched accounts with the registered collectors (SPEC 5, 10.1).

    Returns the ids of the new posts. Each is committed and has its pipeline queued before the next is read. A source
    that fails is recorded on its account and does not stop the others.
    """
    if not registered_platforms():
        logger.info("collect.run_all: no collectors are registered, nothing to collect")
        return []
    accounts = session.scalars(select(SourceAccount).where(SourceAccount.is_watched).order_by(SourceAccount.id)).all()
    return _collect_accounts(session, accounts, client)


def collect_source(session: Session, source_id: int, client: httpx.Client | None = None) -> list[int]:
    """Collect one account now (the «Собрать сейчас» button); the result is as in `run_collectors`."""
    account = session.get(SourceAccount, source_id)
    if account is None:
        logger.warning("collect.source: source account %s does not exist", source_id)
        return []
    return _collect_accounts(session, [account], client)

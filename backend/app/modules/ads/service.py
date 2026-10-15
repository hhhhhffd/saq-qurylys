import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
from celery import chain
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import storage
from app.collectors import default_client
from app.collectors.base import CollectedPost, CollectorError, get_collector, registered_platforms
from app.collectors.media import download_photos
from app.config import get_settings
from app.errors import api_error
from app.models import AdPost, AppUser, ConstructionObject, Evidence, PhraseHit, SourceAccount
from app.models.enums import (
    AdOrigin,
    AdVersionSource,
    CaptureStatus,
    EvidenceKind,
    NotificationKind,
    OcrStatus,
    Platform,
    Role,
)
from app.modules.ads.schemas import AdDetail, AdRow, LinkedObject, PhraseHitOut
from app.modules.ads.urls import handle_from_url
from app.modules.ads.versions import record_version
from app.modules.evidence.schemas import EvidenceOut
from app.modules.nlp.llm import Extraction
from app.modules.nlp.service import finding_for_hit
from app.modules.settings.service import load_settings
from app.modules.signals.notifications import add_notifications, users_covering_territory
from app.scope import TerritoryScope
from app.storage import EvidenceLink
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def get_ad_in_scope(session: Session, scope: TerritoryScope, ad_id: int) -> AdPost:
    """Out-of-scope publications are reported as missing so their existence is not disclosed."""
    ad = session.get(AdPost, ad_id)
    if ad is None or not scope.contains(ad.territory_id):
        raise api_error(404, "ad_not_found", "Публикация не найдена")
    return ad


def build_row(ad: AdPost, object_name: str | None) -> AdRow:
    return AdRow.model_validate(ad).model_copy(update={"object_name": object_name})


def build_detail(session: Session, ad: AdPost) -> AdDetail:
    obj = session.get(ConstructionObject, ad.object_id) if ad.object_id is not None else None
    hits = session.scalars(
        select(PhraseHit).where(PhraseHit.ad_post_id == ad.id).order_by(PhraseHit.start, PhraseHit.id)
    )
    evidence = session.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id).order_by(Evidence.id))
    text = ad.text or ""
    extraction = Extraction.model_validate(ad.llm_extraction) if ad.llm_extraction is not None else None
    return AdDetail(
        **build_row(ad, obj.name if obj else None).model_dump(),
        phrase_hits=[PhraseHitOut.from_hit(hit, text, finding_for_hit(hit, extraction)) for hit in hits],
        evidence=[EvidenceOut.model_validate(item) for item in evidence],
        llm_extraction=extraction,
        linked_object=LinkedObject.model_validate(obj) if obj else None,
    )


def dispatch_pipeline(ad_post_id: int, *, capture: bool, requested_by: int | None) -> bool:
    """Queue the pipeline of a new publication (SPEC 5): capture (when it has a URL), analyze, link, LLM.

    Call after the post is committed. Returns False when the broker is unreachable; the request whose data is
    already saved must not fail because of it.
    """
    if not get_settings().events_enabled:
        return True
    steps: list[tuple[str, str, list[int | None]]] = [
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
    ad.capture_status = CaptureStatus.failed
    ad.capture_error = "Не удалось поставить фиксацию в очередь"
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


def _store_photos(session: Session, ad: AdPost, urls: list[str], client: httpx.Client) -> int:
    """Download the photos of a collected post and keep them as its evidence; returns how many were stored."""
    photos = download_photos(client, urls)
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
    return len(photos)


def ingest_collected_post(
    session: Session,
    account: SourceAccount,
    post: CollectedPost,
    *,
    capture: bool,
    client: httpx.Client | None = None,
) -> AdPost | None:
    """Store a post found by a collector. Flushed, not committed.

    `capture` tells whether the post's URL is opened with the browser. A known post (same platform and external id)
    is not stored again; when its text has changed at the source, the new text is recorded as a version. Returns the
    new post, or None for a known one.
    """
    known = session.scalar(
        select(AdPost).where(AdPost.platform == account.platform, AdPost.external_id == post.external_id)
    )
    if known is not None:
        record_version(session, known, post.text, AdVersionSource.collector, datetime.now(UTC))
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
        author=post.author,
        published_at=post.published_at,
        text=post.text,
        links=post.links,
        capture_status=CaptureStatus.pending if capture and post.url else None,
        origin=AdOrigin.collector,
    )
    session.add(ad)
    session.flush()
    if post.media_urls and _store_photos(session, ad, post.media_urls, client or default_client()):
        ad.ocr_status = OcrStatus.pending
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


def _collect_account(
    session: Session, account: SourceAccount, since: datetime, client: httpx.Client | None
) -> list[AdPost]:
    """Collect one account and record the outcome on it. Commits."""
    collector = get_collector(account.platform)
    if collector is None:
        return []
    started_at = datetime.now(UTC)

    def is_known(external_id: str) -> bool:
        stmt = select(AdPost.id).where(AdPost.platform == account.platform, AdPost.external_id == external_id)
        return session.scalar(stmt) is not None

    ads: list[AdPost] = []
    error: str | None = None
    try:
        for post in collector.collect(account, since, is_known):
            ad = ingest_collected_post(session, account, post, capture=collector.capture_urls, client=client)
            if ad is not None:
                ads.append(ad)
    except CollectorError as exc:
        # The posts read before the failure are kept: the source answered for them.
        error = str(exc)
        logger.warning("Collecting source account %s (%s) failed: %s", account.id, account.platform, error)
    except Exception:
        logger.exception("Collecting source account %s (%s) failed", account.id, account.platform)
        session.rollback()
        ads = []
        error = "Непредвиденная ошибка сбора, подробности в журнале сервера"
    if error is None:
        account.last_collected_at = started_at
        account.last_error = None
        account.last_error_at = None
    else:
        if account.last_error is None:
            _notify_collector_failed(session, account, error)
        account.last_error = error
        account.last_error_at = started_at
    session.commit()
    return ads


def _collect_accounts(
    session: Session, accounts: Sequence[SourceAccount], client: httpx.Client | None
) -> list[tuple[int, bool]]:
    default_since = datetime.now(UTC) - timedelta(days=load_settings(session).ad_window_days)
    created: list[tuple[int, bool]] = []
    for account in accounts:
        collector = get_collector(account.platform)
        if collector is None or not collector.handles(account):
            continue
        ads = _collect_account(session, account, account.last_collected_at or default_since, client)
        created.extend((ad.id, ad.capture_status is CaptureStatus.pending) for ad in ads)
    return created


def run_collectors(session: Session, client: httpx.Client | None = None) -> list[tuple[int, bool]]:
    """Collect new posts of the watched accounts with the registered collectors (SPEC 5, 10.1).

    Returns (ad_post id, whether to capture its page) of the new posts, committed; the caller queues their pipeline.
    A source that fails is recorded on its account and does not stop the others.
    """
    if not registered_platforms():
        logger.info("collect.run_all: no collectors are registered, nothing to collect")
        return []
    accounts = session.scalars(select(SourceAccount).where(SourceAccount.is_watched).order_by(SourceAccount.id)).all()
    return _collect_accounts(session, accounts, client)


def collect_source(session: Session, source_id: int, client: httpx.Client | None = None) -> list[tuple[int, bool]]:
    """Collect one account now (the «Собрать сейчас» button); the result is as in `run_collectors`."""
    account = session.get(SourceAccount, source_id)
    if account is None:
        logger.warning("collect.source: source account %s does not exist", source_id)
        return []
    return _collect_accounts(session, [account], client)

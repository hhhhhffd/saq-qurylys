import logging
from datetime import UTC, datetime, timedelta

from celery import chain
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.collectors.base import CollectedPost, get_collector, registered_platforms
from app.config import get_settings
from app.errors import api_error
from app.models import AdPost, ConstructionObject, Evidence, PhraseHit, SourceAccount
from app.models.enums import AdOrigin, CaptureStatus, Platform
from app.modules.ads.schemas import AdDetail, AdRow, LinkedObject, PhraseHitOut
from app.modules.ads.urls import handle_from_url
from app.modules.evidence.schemas import EvidenceOut
from app.modules.nlp.llm import Extraction
from app.modules.nlp.service import finding_for_hit
from app.modules.settings.service import load_settings
from app.scope import TerritoryScope
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


def ingest_collected_post(session: Session, account: SourceAccount, post: CollectedPost) -> AdPost | None:
    """Store a post found by a collector unless it is known already. Flushed, not committed."""
    known = session.scalar(
        select(AdPost.id).where(AdPost.platform == account.platform, AdPost.external_id == post.external_id)
    )
    if known is not None:
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
        capture_status=CaptureStatus.pending if post.url else None,
        origin=AdOrigin.collector,
    )
    session.add(ad)
    session.flush()
    return ad


def run_collectors(session: Session) -> list[tuple[int, bool]]:
    """Collect new posts of the watched accounts with the registered collectors (SPEC 5, phase 2).

    Returns (ad_post id, has URL) of the new posts, committed; the caller queues their pipeline.
    """
    if not registered_platforms():
        logger.info("collect.run_all: no collectors are registered (phase 2), nothing to collect")
        return []
    default_since = datetime.now(UTC) - timedelta(days=load_settings(session).ad_window_days)
    created: list[tuple[int, bool]] = []
    for account in session.scalars(select(SourceAccount).where(SourceAccount.is_watched)).all():
        collector = get_collector(account.platform)
        if collector is None:
            continue
        started_at = datetime.now(UTC)
        try:
            ads = [
                ad
                for post in collector.collect(account, account.last_collected_at or default_since)
                if (ad := ingest_collected_post(session, account, post)) is not None
            ]
            account.last_collected_at = started_at
            session.commit()
        except Exception:
            logger.exception("collect.run_all: collecting account %s (%s) failed", account.id, account.platform)
            session.rollback()
            continue
        created.extend((ad.id, ad.url is not None) for ad in ads)
    return created

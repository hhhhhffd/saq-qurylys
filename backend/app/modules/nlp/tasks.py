import logging

from app.db import get_sessionmaker
from app.events import object_changed, objects_changed
from app.models import AdPost
from app.models.enums import LlmStatus
from app.modules.nlp import service
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="nlp.analyze")
def analyze(ad_post_id: int) -> None:
    with get_sessionmaker()() as session:
        ad = session.get(AdPost, ad_post_id)
        if ad is None:
            logger.warning("nlp.analyze: ad_post %s does not exist", ad_post_id)
            return
        service.analyze_ad(session, ad)
        session.commit()


@celery_app.task(name="nlp.link")
def link(ad_post_id: int) -> None:
    with get_sessionmaker()() as session:
        ad = session.get(AdPost, ad_post_id)
        if ad is None:
            logger.warning("nlp.link: ad_post %s does not exist", ad_post_id)
            return
        previous, current = service.link_ad(session, ad)
        session.commit()
    if previous != current:
        objects_changed(object_id for object_id in (previous, current) if object_id is not None)


@celery_app.task(name="nlp.llm_extract")
def llm_extract(ad_post_id: int) -> None:
    """Last step of the ad pipeline: the object is rescored once everything about the post is known."""
    with get_sessionmaker()() as session:
        ad = session.get(AdPost, ad_post_id)
        if ad is None:
            logger.warning("nlp.llm_extract: ad_post %s does not exist", ad_post_id)
            return
        try:
            service.llm_extract_ad(session, ad)
        except Exception:
            logger.exception("nlp.llm_extract: unexpected failure for ad_post %s", ad_post_id)
            session.rollback()
            ad = session.get(AdPost, ad_post_id)
            if ad is not None:
                ad.llm_status = LlmStatus.failed
        session.commit()
        object_id = ad.object_id if ad is not None else None
    if object_id is not None:
        object_changed(object_id)


@celery_app.task(name="nlp.reanalyze_recent")
def reanalyze_recent() -> int:
    """Event-triggered after a dictionary change (no schedule): analyze the recent posts again."""
    posts = 0
    objects: set[int] = set()
    with get_sessionmaker()() as session:
        for affected in service.reanalyze_recent(session):
            objects_changed(affected)
            objects |= affected
            posts += 1
    logger.info("nlp.reanalyze_recent: %s batches, %s objects to recalculate", posts, len(objects))
    return posts

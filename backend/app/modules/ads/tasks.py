import logging

import httpx

from app import collectors
from app.config import get_settings
from app.db import get_sessionmaker
from app.events import objects_changed
from app.modules.ads import recheck, service
from app.modules.ads.capture import USER_AGENT, capture_ad
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# A capture is bounded by the browser timeouts; the limits stop a hung browser from holding the worker.
CAPTURE_SOFT_LIMIT_S = 150
CAPTURE_HARD_LIMIT_S = 180

# The collectors that are switched on in `.env` are registered when the worker loads its tasks.
collectors.register_enabled(get_settings(), collectors.default_client())


@celery_app.task(name="archive.capture", soft_time_limit=CAPTURE_SOFT_LIMIT_S, time_limit=CAPTURE_HARD_LIMIT_S)
def capture(ad_post_id: int, requested_by: int | None = None) -> None:
    with get_sessionmaker()() as session:
        capture_ad(session, ad_post_id, requested_by)


@celery_app.task(name="ads.recheck_due")
def recheck_due() -> None:
    with (
        get_sessionmaker()() as session,
        httpx.Client(timeout=recheck.CHECK_TIMEOUT_S, headers={"User-Agent": USER_AGENT}) as client,
    ):
        removed_objects = recheck.recheck_due(session, client)
        # The ad window slides with time: claims that fell out of it no longer count.
        refreshed_objects = service.refresh_all_claimed_readiness(session)
        session.commit()
    objects_changed([*removed_objects, *refreshed_objects])


def _dispatch_new_posts(created: list[tuple[int, bool]]) -> None:
    for ad_post_id, capture in created:
        service.dispatch_pipeline(ad_post_id, capture=capture, requested_by=None)


@celery_app.task(name="collect.run_all")
def run_all() -> None:
    with get_sessionmaker()() as session:
        created = service.run_collectors(session)
    _dispatch_new_posts(created)


@celery_app.task(name="collect.source")
def collect_source(source_id: int) -> None:
    with get_sessionmaker()() as session:
        created = service.collect_source(session, source_id)
    _dispatch_new_posts(created)

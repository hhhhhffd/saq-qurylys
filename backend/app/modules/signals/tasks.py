import logging

from app.db import get_sessionmaker
from app.modules.signals.service import check_deadlines
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="signals.check_deadlines")
def check_deadlines_task() -> int:
    """Daily: `signal_due_soon` / `signal_overdue` notifications for cards waiting for an answer."""
    with get_sessionmaker()() as session:
        created = check_deadlines(session)
        session.commit()
    logger.info("signals.check_deadlines: %s notifications created", created)
    return created

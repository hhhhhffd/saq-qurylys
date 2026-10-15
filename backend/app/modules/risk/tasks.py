import logging
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.models import ConstructionObject
from app.models.enums import Recipient, ScoreTrigger
from app.modules.risk.service import dispatch_red_zone, notify_red_zone, recalculate
from app.modules.settings.service import load_settings
from app.modules.signals import mail
from app.modules.signals.labels import RED_ZONE_DISCLAIMER
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def recalc_and_commit(session: Session, object_id: int, trigger: ScoreTrigger) -> bool:
    """Recalculate one object in its own transaction and announce an entry into the red zone."""
    result = recalculate(session, object_id, trigger)
    if result is None:
        logger.warning("Object %s no longer exists; nothing to recalculate", object_id)
        return False
    session.commit()
    if result.entered_red:
        dispatch_red_zone(object_id)
    return True


@celery_app.task(name="risk.recalc_object")
def recalc_object(object_id: int, trigger: str = ScoreTrigger.event.value) -> None:
    with get_sessionmaker()() as session:
        recalc_and_commit(session, object_id, ScoreTrigger(trigger))


@celery_app.task(name="risk.sweep_due")
def sweep_due() -> int:
    """Recalculate objects whose scheduled check has come (or that were never scored). One object failing
    does not stop the others; it keeps its old `next_check_at` and is retried by the next sweep."""
    done = failed = 0
    with get_sessionmaker()() as session:
        due_ids = list(
            session.scalars(
                select(ConstructionObject.id)
                .where(
                    or_(
                        ConstructionObject.next_check_at.is_(None),
                        ConstructionObject.next_check_at <= datetime.now(UTC),
                    )
                )
                .order_by(ConstructionObject.next_check_at.nulls_first(), ConstructionObject.id)
            )
        )
        for object_id in due_ids:
            try:
                done += recalc_and_commit(session, object_id, ScoreTrigger.schedule)
            except Exception:
                session.rollback()
                failed += 1
                logger.exception("Scheduled recalculation of object %s failed", object_id)
    logger.info("risk.sweep_due: %s recalculated, %s failed", done, failed)
    return done


@celery_app.task(name="notify.red_zone")
def red_zone(object_id: int) -> int:
    """Tell the responsible mio officers that an object entered the red zone; mail the MIO addresses if SMTP is set."""
    with get_sessionmaker()() as session:
        notice = notify_red_zone(session, object_id)
        emails = load_settings(session).recipient_emails.get(Recipient.mio, []) if notice and notice.notified else []
        session.commit()
    if notice is None:
        return 0
    if emails:
        mail.send_email(
            emails,
            f"Красная зона: {notice.object_name}",
            f"Объект {notice.object_code} «{notice.object_name}» ({notice.address or 'адрес не указан'}) "
            f"переведён в красную зону, балл риска {notice.score}. Подробности в системе.\n\n{RED_ZONE_DISCLAIMER}",
        )
    return notice.notified

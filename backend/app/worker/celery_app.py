import pkgutil

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

import app.modules
from app.config import get_settings

settings = get_settings()

celery_app = Celery("saq_qurylys", broker=settings.redis_url, backend=settings.redis_url)

QUEUES = ("collect", "archive", "nlp", "score", "notify", "default")

# Task names are the contract between modules; each module implements its own in `<module>/tasks.py`.
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    result_expires=3600,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # tasks are long (browser capture, LLM): do not hoard them
    broker_connection_retry_on_startup=True,
    # Fail fast when the API enqueues during a broker outage (default: ~20 s of retries per call).
    broker_transport_options={"socket_connect_timeout": 2, "max_retries": 1, "interval_start": 0, "interval_step": 0.2},
    task_default_queue="default",
    # One direct exchange per queue; a bare Queue(name) would bind all queues to the shared "default" key
    # and every message would be delivered to every queue.
    task_queues=[Queue(name, Exchange(name, type="direct"), routing_key=name) for name in QUEUES],
    task_routes={
        "archive.capture": {"queue": "archive"},
        "nlp.analyze": {"queue": "nlp"},
        "nlp.link": {"queue": "nlp"},
        "nlp.llm_extract": {"queue": "nlp"},
        "nlp.ocr": {"queue": "nlp"},
        "ads.recheck_due": {"queue": "collect"},
        "collect.run_all": {"queue": "collect"},
        "collect.source": {"queue": "collect"},
        "registry.sync_homeportal": {"queue": "collect"},
        "risk.recalc_object": {"queue": "score"},
        "risk.sweep_due": {"queue": "score"},
        "signals.check_deadlines": {"queue": "notify"},
        "notify.red_zone": {"queue": "notify"},
    },
    beat_schedule={
        "collect-run-all": {"task": "collect.run_all", "schedule": crontab(hour=1, minute=0)},
        "risk-sweep-due": {"task": "risk.sweep_due", "schedule": crontab(hour=2, minute=0)},
        # Does nothing unless HOMEPORTAL_SYNC_ENABLED=true (needs the agreement of АО «КЖК», OPEN_QUESTIONS 11).
        "registry-sync-homeportal": {
            "task": "registry.sync_homeportal",
            "schedule": crontab(hour=3, minute=0),
            "kwargs": {"scheduled": True},
        },
        "ads-recheck-due": {"task": "ads.recheck_due", "schedule": crontab(hour="*/6", minute=15)},
        "signals-check-deadlines": {"task": "signals.check_deadlines", "schedule": crontab(hour=6, minute=0)},
    },
)

# Every package under app/modules may define tasks.py; a missing tasks.py is ignored.
celery_app.autodiscover_tasks([f"app.modules.{module.name}" for module in pkgutil.iter_modules(app.modules.__path__)])

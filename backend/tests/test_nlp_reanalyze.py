from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdPost, AuditLog, Phrase, PhraseHit
from app.models.enums import DetectedBy, PhraseCategory
from app.modules.nlp import service, tasks
from tests.conftest import World, auth, make_object
from tests.support_ads import add_ad
from tests.test_nlp_service import SessionFactory


def hits_of(db: Session, ad: AdPost) -> list[PhraseHit]:
    return list(db.scalars(select(PhraseHit).where(PhraseHit.ad_post_id == ad.id).order_by(PhraseHit.start)))


def phrase(db: Session, category: PhraseCategory, text: str, weight: int = 9, **fields: Any) -> Phrase:
    row = Phrase(category=category, text=text, variants=[], weight=weight, **fields)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Enable the Celery hooks and record what is sent instead of using the broker."""
    sent: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr("app.events.celery_app.send_task", lambda name, args=(), **kwargs: sent.append((name, kwargs)))
    return sent


# ---------------------------------------------------------------- analysis result


def test_analyze_reports_whether_the_dictionary_hits_changed(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, "Предоплата за квартиру, бронь открыта")
    assert service.analyze_ad(db, ad) is True  # the booking hit is new
    assert service.analyze_ad(db, ad) is False

    deposit = phrase(db, PhraseCategory.deposit, "предоплата")
    assert service.analyze_ad(db, ad) is True  # a new phrase matches
    deposit.weight = 11
    assert service.analyze_ad(db, ad) is True  # the weight of a hit changed
    deposit.category = PhraseCategory.down_payment
    assert service.analyze_ad(db, ad) is True  # so did the category
    deposit.is_active = False
    assert service.analyze_ad(db, ad) is True  # the phrase is gone
    assert service.analyze_ad(db, ad) is False


# ---------------------------------------------------------------- re-analysis of recent posts


def test_reanalysis_covers_recent_posts_keeps_confirmations_and_names_affected_objects(
    db: Session, world: World
) -> None:
    now = datetime.now(UTC)
    changed_obj = make_object(db, world.ust, "ЖК Затронутый")
    unchanged_obj = make_object(db, world.ust, "ЖК Прежний")
    recent = add_ad(db, world.ust, "Внесите предоплату, бронь открыта", object_id=changed_obj.id, published_at=now)
    unaffected = add_ad(db, world.ust, "Просто текст", object_id=unchanged_obj.id, published_at=now)
    captured_only = add_ad(db, world.ust, "Нужна предоплата", captured_at=now - timedelta(days=10))
    old = add_ad(db, world.ust, "Нужна предоплата", published_at=now - timedelta(days=200))
    no_text = add_ad(db, world.ust, None)
    for ad in (recent, unaffected, captured_only, old, no_text):
        service.analyze_ad(db, ad)
    [booking_hit] = hits_of(db, recent)
    booking_hit.confirmed = True
    deposit = phrase(db, PhraseCategory.deposit, "предоплата", weight=13)

    batches = list(service.reanalyze_recent(db))

    assert batches == [{changed_obj.id}]
    assert {(hit.category, hit.weight) for hit in hits_of(db, recent)} == {
        (PhraseCategory.deposit, 13),
        (PhraseCategory.booking, 10),
    }
    assert db.get(PhraseHit, booking_hit.id) is not None and booking_hit.confirmed is True
    assert recent.max_phrase_weight == 13
    assert [hit.phrase_id for hit in hits_of(db, captured_only)] == [deposit.id]
    assert hits_of(db, old) == [] and hits_of(db, unaffected) == [] and hits_of(db, no_text) == []

    assert list(service.reanalyze_recent(db)) == [set()]  # nothing changed the second time


def test_reanalysis_removes_hits_of_deactivated_phrases_and_works_in_batches(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "REANALYZE_BATCH_SIZE", 2)
    objects = [make_object(db, world.ust, f"ЖК {number}") for number in range(5)]
    ads = [add_ad(db, world.ust, "Бронь квартир", object_id=obj.id) for obj in objects]
    for ad in ads:
        service.analyze_ad(db, ad)
    booking = db.scalars(select(Phrase).where(Phrase.category == PhraseCategory.booking)).one()
    booking.is_active = False

    batches = list(service.reanalyze_recent(db))

    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert set().union(*batches) == {obj.id for obj in objects}
    assert all(hits_of(db, ad) == [] and ad.max_phrase_weight == 0 for ad in ads)


def test_reanalysis_leaves_llm_hits_alone(db: Session, world: World) -> None:
    ad = add_ad(db, world.ust, "Оставьте залог")
    llm_hit = PhraseHit(
        ad_post_id=ad.id,
        category=PhraseCategory.deposit,
        matched_text="залог",
        start=9,
        end=14,
        weight=10,
        detected_by=DetectedBy.llm,
    )
    db.add(llm_hit)
    db.flush()

    assert list(service.reanalyze_recent(db)) == [set()]
    assert db.get(PhraseHit, llm_hit.id) is not None


def test_task_asks_for_a_recalculation_of_each_batch(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    recalculated: list[list[int]] = []
    monkeypatch.setattr(service, "REANALYZE_BATCH_SIZE", 1)
    monkeypatch.setattr(tasks, "get_sessionmaker", lambda: SessionFactory(db))
    monkeypatch.setattr(tasks, "objects_changed", lambda ids: recalculated.append(sorted(ids)))
    first = make_object(db, world.ust, "ЖК Один")
    second = make_object(db, world.ust, "ЖК Два")
    for obj in (first, second):
        add_ad(db, world.ust, "Бронь квартир", object_id=obj.id)

    assert tasks.reanalyze_recent() == 2

    assert recalculated == [[first.id], [second.id]]


# ---------------------------------------------------------------- triggers


def test_dictionary_changes_queue_the_reanalysis(
    client: TestClient, db: Session, world: World, queued: list[tuple[str, dict[str, Any]]]
) -> None:
    admin = auth(world.users["admin"])
    created = client.post(
        "/api/v1/phrases", headers=admin, json={"text": "Предоплата", "category": "deposit", "weight": 9}
    )
    assert created.status_code == 201
    phrase_id = created.json()["id"]
    assert client.patch(f"/api/v1/phrases/{phrase_id}", headers=admin, json={"weight": 12}).status_code == 200

    assert [name for name, _ in queued] == ["nlp.reanalyze_recent"] * 2
    assert queued[0][1]["queue"] == "nlp"

    # Rejected changes do not trigger it.
    queued.clear()
    duplicate = client.post(
        "/api/v1/phrases", headers=admin, json={"text": "предоплата", "category": "deposit", "weight": 9}
    )
    assert duplicate.status_code == 409
    assert client.patch(f"/api/v1/phrases/{phrase_id}", headers=admin, json={"weight": None}).status_code == 422
    assert client.patch("/api/v1/phrases/999999999", headers=admin, json={"weight": 1}).status_code == 404
    assert (
        client.post(
            "/api/v1/phrases",
            headers=auth(world.users["mio_ust"]),
            json={"text": "x", "category": "deposit", "weight": 1},
        ).status_code
        == 403
    )
    assert queued == []


def test_a_broker_outage_does_not_fail_the_dictionary_change(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("broker is down")

    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr("app.events.celery_app.send_task", down)
    admin = auth(world.users["admin"])

    created = client.post(
        "/api/v1/phrases", headers=admin, json={"text": "Предоплата", "category": "deposit", "weight": 9}
    )
    assert created.status_code == 201

    manual = client.post("/api/v1/phrases/reanalyze", headers=admin)
    assert manual.status_code == 503 and manual.json()["detail"]["code"] == "queue_unavailable"


def test_manual_reanalysis_is_for_the_global_admin(
    client: TestClient, db: Session, world: World, queued: list[tuple[str, dict[str, Any]]]
) -> None:
    for key in ("mio_ust", "mio_region", "admin_semey", "gask"):
        assert client.post("/api/v1/phrases/reanalyze", headers=auth(world.users[key])).status_code == 403, key
    assert client.post("/api/v1/phrases/reanalyze").status_code == 401
    assert queued == []

    response = client.post("/api/v1/phrases/reanalyze", headers=auth(world.users["admin"]))

    assert response.status_code == 202 and response.json() == {"queued": True}
    assert queued == [("nlp.reanalyze_recent", {"queue": "nlp", "retry": False, "ignore_result": True})]
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "phrase.reanalyze")).one()
    assert entry.user_id == world.users["admin"].id

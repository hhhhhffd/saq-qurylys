"""The demo publication that was edited and deleted at its source (SPEC 10.6), and the demo scenarios around it."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import seed, seed_versions, storage
from app.models import AdPost, AdPostVersion, AppUser, ConstructionObject, Developer, District, Evidence, LinkedEntity
from app.models.enums import AdOrigin, AdStatus, AdVersionSource, CaptureStatus, EvidenceKind, ScoreTrigger, Zone
from app.modules.ads import service
from app.modules.nlp.service import analyze_ad
from app.modules.risk.service import recalculate
from app.scope import build_scope
from tests.test_seed_demo import EXPECTED

NAME = "ЖК «Малахит»"
DATA = json.loads((seed.SEED_DATA_DIR / seed_versions.FILE_NAME).read_text(encoding="utf-8"))


@pytest.fixture
def demo(db: Session, bucket: str) -> list[int]:
    seed.seed_reference(db)
    seed.load_districts(db)
    seed.seed_demo_users(db)
    return seed.seed_demo_objects(db)


def _publication(db: Session) -> AdPost:
    obj = db.scalars(select(ConstructionObject).where(ConstructionObject.name == NAME)).one()
    return db.scalars(select(AdPost).where(AdPost.object_id == obj.id)).one()


def test_the_demo_publication_keeps_its_original_its_edit_and_the_moment_it_was_deleted(
    db: Session, demo: list[int]
) -> None:
    [object_id] = seed_versions.seed_demo_versions(db)

    obj = db.get(ConstructionObject, object_id)
    ad = _publication(db)
    assert obj is not None and obj.is_demo and ad.is_demo and ad.object_id == object_id
    assert ad.status is AdStatus.removed_saved and ad.capture_status is CaptureStatus.done
    assert ad.origin is AdOrigin.capture and ad.url is not None and ad.url.startswith("https://example.invalid/")
    assert ad.text is not None and "Бронь квартиры за 10%" in ad.text  # the saved original

    assert ad.captured_at is not None and ad.removed_detected_at is not None
    now = datetime.now(UTC)
    assert now - ad.captured_at == pytest.approx(timedelta(hours=90), abs=timedelta(minutes=5))
    assert ad.removed_detected_at - ad.captured_at == timedelta(hours=2, minutes=15)
    assert ad.removed_detected_at < now and ad.last_checked_at == ad.removed_detected_at
    assert ad.published_at is not None and ad.published_at < ad.captured_at

    [version] = db.scalars(select(AdPostVersion).where(AdPostVersion.ad_post_id == ad.id))
    assert version.source is AdVersionSource.capture
    assert version.observed_at - ad.captured_at == timedelta(hours=1, minutes=15)
    assert "Бронь" not in version.text and "Скоро старт продаж" in version.text
    assert version.text_sha256 == hashlib.sha256(version.text.encode()).hexdigest()

    shots = list(
        db.scalars(select(Evidence).where(Evidence.ad_post_id == ad.id, Evidence.kind == EvidenceKind.screenshot_png))
    )
    original_shot, edited_shot = sorted(shots, key=lambda row: row.captured_at)
    assert original_shot.captured_at == ad.captured_at and edited_shot.captured_at == version.observed_at
    assert version.evidence_id == edited_shot.id
    for row, file_name in (
        (original_shot, DATA["history"]["original_screenshot"]),
        (edited_shot, DATA["history"]["versions"][0]["screenshot"]),
    ):
        stored = storage.open_evidence(row)
        try:
            body = bytes(stored.read())
        finally:
            stored.close()
            stored.release_conn()
        assert body == (seed.SEED_DATA_DIR / file_name).read_bytes()
        assert row.sha256 == hashlib.sha256(body).hexdigest() and row.size_bytes == len(body)

    demo_mio = db.scalars(select(AppUser).where(AppUser.username == "demo_mio")).one()
    detail = service.build_detail(db, ad, build_scope(db, demo_mio))
    assert [(v.id, v.evidence_id) for v in detail.versions] == [(version.id, edited_shot.id)]
    assert detail.original_captured_at == ad.captured_at
    assert detail.original_evidence is not None and detail.original_evidence.id == original_shot.id
    assert detail.original_evidence.has_tsa_token is False  # a token cannot be backdated


def test_loading_the_demo_publication_again_adds_nothing(db: Session, demo: list[int]) -> None:
    assert len(seed_versions.seed_demo_versions(db)) == 1
    counts = [
        db.scalar(select(func.count()).select_from(model))
        for model in (ConstructionObject, AdPost, AdPostVersion, Evidence)
    ]

    assert seed_versions.seed_demo_versions(db) == []

    assert counts == [
        db.scalar(select(func.count()).select_from(model))
        for model in (ConstructionObject, AdPost, AdPostVersion, Evidence)
    ]
    assert db.scalar(select(func.count()).select_from(Developer).where(Developer.bin == "992740000104")) == 1


def test_existing_demo_scenarios_keep_their_scores_next_to_the_new_publication(db: Session, demo: list[int]) -> None:
    [new_object_id] = seed_versions.seed_demo_versions(db)
    for ad in db.scalars(select(AdPost)):
        analyze_ad(db, ad)  # what nlp.analyze does for every demo ad
    result: dict[str, Any] = {}
    for object_id in [*demo, new_object_id]:
        recalculate(db, object_id, ScoreTrigger.manual)
        obj = db.get(ConstructionObject, object_id)
        assert obj is not None and obj.zone is not None and obj.score is not None
        result[obj.name] = (obj.score, obj.zone)

    # The case scenarios: A is 35 yellow (R2 + R3), B is 70 red (R1 + R2 + R3), C is 10 green (R3).
    assert result["ЖК «Северный бриз»"] == (35, Zone.yellow)
    assert result["ЖК «Золотая осень»"] == (70, Zone.red)
    assert result["ЖК «Тихая гавань»"] == (10, Zone.green)
    # Nothing else moved; the deleted post still counts: its saved original offers a booking (R2 + R3).
    assert result == {**EXPECTED, NAME: (35, Zone.yellow)}


def test_the_new_object_shares_no_phone_or_name_with_the_existing_demo(db: Session, demo: list[int]) -> None:
    """A phone or a name of the new object found elsewhere would re-link other ads to it and move other scores."""
    [new_object_id] = seed_versions.seed_demo_versions(db)
    new_ad = _publication(db)
    new_developer = db.scalars(select(Developer).where(Developer.bin == "992740000104")).one()
    new_phones = {
        *new_ad.phones,
        *new_developer.phones,
        *db.scalars(select(LinkedEntity.value).where(LinkedEntity.object_id == new_object_id)),
    }
    assert new_phones == {"+77000009100", "+77000009101"}  # the developer's and the sales office's

    other_phones = {
        *(phone for ad in db.scalars(select(AdPost).where(AdPost.id != new_ad.id)) for phone in ad.phones),
        *(
            phone
            for dev in db.scalars(select(Developer).where(Developer.id != new_developer.id))
            for phone in dev.phones
        ),
        *db.scalars(select(LinkedEntity.value).where(LinkedEntity.object_id != new_object_id)),
    }
    assert new_phones.isdisjoint(other_phones)

    others = db.scalars(select(ConstructionObject).where(ConstructionObject.id != new_object_id)).all()
    assert all("малахит" not in " ".join([obj.name, *obj.aliases]).lower() for obj in others)
    assert not any("Малахит" in (ad.text or "") for ad in db.scalars(select(AdPost).where(AdPost.id != new_ad.id)))


def test_the_new_object_lies_in_its_district(db: Session, demo: list[int]) -> None:
    [new_object_id] = seed_versions.seed_demo_versions(db)
    inside = db.scalar(
        select(func.count())
        .select_from(ConstructionObject)
        .join(District, District.id == ConstructionObject.district_id)
        .where(ConstructionObject.id == new_object_id, func.ST_Contains(District.boundary, ConstructionObject.location))
    )
    assert inside == 1


class SessionFactory:
    """Stands in for the sessionmaker so that `seed.run` works inside the test transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def __call__(self) -> "SessionFactory":
        return self

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *args: object) -> None:
        return None


def test_the_demo_run_loads_the_publication_and_queues_its_processing(
    db: Session, bucket: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    queued: list[tuple[list[tuple[int, int]], list[int]]] = []
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: SessionFactory(db))
    monkeypatch.setattr(seed, "dispatch_demo_processing", lambda ads, without_ads: queued.append((ads, without_ads)))

    seed.run(demo=True)

    ad = _publication(db)
    [(ads, objects_without_ads)] = queued
    assert (ad.id, ad.object_id) in ads and ad.object_id not in objects_without_ads
    assert db.scalar(select(func.count()).select_from(AdPostVersion).where(AdPostVersion.ad_post_id == ad.id)) == 1
    capsys.readouterr()  # the demo user passwords printed by the run

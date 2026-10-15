import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import seed
from app.config import get_settings
from app.models import AdPost, Complaint, ConstructionObject, Developer, District, Document, PhraseHit
from app.models.enums import CheckStatus, DocType, PhraseCategory, ScoreTrigger, Zone
from app.modules.nlp.service import analyze_ad
from app.modules.risk.service import recalculate

DEMO_FILE = seed.SEED_DATA_DIR / "demo_objects.json"
DEMO = json.loads(DEMO_FILE.read_text(encoding="utf-8"))

# Expected outcome of the case model (SPEC 6): score and zone per demo object. A, B and C are the control
# scenarios of the case (6.6).
EXPECTED: dict[str, tuple[int, Zone]] = {
    "ЖК «Северный бриз»": (35, Zone.yellow),  # A: legal basis unknown + paid booking
    "ЖК «Золотая осень»": (70, Zone.red),  # B: absence of the basis established + deposit
    "ЖК «Тихая гавань»": (10, Zone.green),  # C: guarantee confirmed + ordinary advertising
    "ЖК «Тополиная аллея»": (25, Zone.yellow),  # R4: verified collective complaint
    "ЖК «Кедровый квартал»": (45, Zone.yellow),  # R5: claimed 70% against 35% at the inspection
    "ЖК «Звёздный путь»": (5, Zone.green),  # R6: stalled; the unverified complaint is only a flag
    "ЖК «Новая эра»": (15, Zone.green),  # R6: delayed
    "ЖК «Облачный»": (10, Zone.green),  # legal basis being checked: a flag, no points
    "ЖК «Берёзовая роща»": (0, Zone.green),
    "ЖК «Янтарный двор»": (10, Zone.green),
    "ЖК «Лазурный берег»": (35, Zone.yellow),
    "ЖК «Эдельвейс»": (35, Zone.yellow),  # R1 alone is not red
    "ЖК «Хрустальный город»": (70, Zone.red),
    "ЖК «Радужный парк»": (0, Zone.green),
    "ЖК «Серебряный ручей»": (0, Zone.green),
    "ЖК «Солнечная долина»": (0, Zone.green),
}


@pytest.fixture
def demo(db: Session) -> list[int]:
    seed.seed_reference(db)
    seed.load_districts(db)
    seed.seed_demo_users(db)
    return seed.seed_demo_objects(db)


def _by_name(db: Session, name: str) -> ConstructionObject:
    return db.scalars(select(ConstructionObject).where(ConstructionObject.name == name)).one()


def _ads(db: Session, obj: ConstructionObject) -> list[AdPost]:
    return list(db.scalars(select(AdPost).where(AdPost.object_id == obj.id).order_by(AdPost.id)))


def _hit_categories(db: Session, ad: AdPost) -> set[PhraseCategory]:
    return set(db.scalars(select(PhraseHit.category).where(PhraseHit.ad_post_id == ad.id)))


def test_relative_dates_follow_the_moment_of_loading() -> None:
    today = datetime.now(seed.ZoneInfo(seed.TIMEZONE)).date()
    assert seed._resolve_date("-2d") == today - timedelta(days=2)
    assert seed._resolve_date("+330d") == today + timedelta(days=330)
    assert seed._resolve_date("2026-05-01") == "2026-05-01"  # absolute dates pass through to the normal parser
    moment = seed._resolve_datetime("-36h")
    assert abs((datetime.now(UTC) - timedelta(hours=36) - moment).total_seconds()) < 5
    assert seed._resolve_datetime("-2 days") == "-2 days"  # not a relative form: left for validation to reject


def test_demo_file_is_fictional_and_complete() -> None:
    objects = DEMO["objects"]
    ads = [ad for obj in objects for ad in obj["ads"]]
    assert len(objects) >= 8 and len(ads) >= 12
    for developer in DEMO["developers"]:
        assert re.fullmatch(r"99[0-9]{10}", developer["bin"]), "fictional BINs start with 99"
        assert all(re.fullmatch(r"\+7 700 000 \d\d \d\d", phone) for phone in developer["phones"])
    for obj in objects:
        assert obj["documents"] is not None and obj["inspections"] and obj["linked_entities"] and obj["developer_bin"]
        assert all(re.fullmatch(r"\+7700000\d{4}", entity["value"]) for entity in obj["linked_entities"])
    for ad in ads:
        assert ad["url"] is None or ad["url"].startswith("https://example.invalid/")
        assert re.fullmatch(r"-([1-9]|1\d|20)d", ad["published_at"]), "dated 1-20 days before loading"
        assert re.search(r"\+7 700 000 \d\d \d\d", ad["text"])
    assert {ad["platform"] for ad in ads} >= {"telegram", "instagram", "website", "outdoor"}
    assert sum(1 for ad in ads if ad["is_outdoor"]) >= 2
    assert all(ad["lat"] is not None and ad["lon"] is not None for ad in ads if ad["is_outdoor"])


def test_unknown_keys_are_rejected(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed.seed_reference(db)
    (tmp_path / "demo_objects.json").write_text(json.dumps({"objects": [{"name": "ЖК Тест", "surprise": 1}]}))
    monkeypatch.setattr(seed, "SEED_DATA_DIR", tmp_path)
    with pytest.raises(SystemExit, match="surprise"):
        seed.seed_demo_objects(db)


def test_demo_is_marked_and_loaded_once(db: Session, demo: list[int]) -> None:
    assert len(demo) == len(DEMO["objects"]) == len(EXPECTED)
    assert (
        db.scalar(select(func.count()).select_from(ConstructionObject).where(ConstructionObject.is_demo.is_(False)))
        == 0
    )
    assert db.scalar(select(func.count()).select_from(AdPost).where(AdPost.is_demo.is_(False))) == 0
    assert db.scalar(select(func.count()).select_from(AdPost)) == sum(len(o["ads"]) for o in DEMO["objects"])
    assert seed.seed_demo_objects(db) == []
    assert db.scalar(select(func.count()).select_from(Developer)) == len(DEMO["developers"])


def test_demo_dates_are_relative_to_loading(db: Session, demo: list[int]) -> None:
    now = datetime.now(UTC)
    for ad in db.scalars(select(AdPost)):
        assert ad.published_at is not None
        assert timedelta(days=1) - timedelta(minutes=1) <= now - ad.published_at <= timedelta(days=20, minutes=1)
    stalled = _by_name(db, "ЖК «Звёздный путь»")
    assert stalled.stalled_since is not None and (date.today() - stalled.stalled_since).days >= 30
    delayed = _by_name(db, "ЖК «Новая эра»")
    assert delayed.planned_completion is not None and (date.today() - delayed.planned_completion).days > 90


def test_demo_districts_match_the_points(db: Session, demo: list[int]) -> None:
    outside = db.scalar(
        select(func.count())
        .select_from(ConstructionObject)
        .join(District, District.id == ConstructionObject.district_id)
        .where(func.ST_Contains(District.boundary, ConstructionObject.location).is_not(True))
    )
    assert outside == 0
    assert (
        db.scalar(select(func.count()).select_from(ConstructionObject).where(ConstructionObject.district_id.is_(None)))
        == 0
    )


def test_control_scenarios_are_named_and_documented_as_the_case_requires(db: Session, demo: list[int]) -> None:
    a, b, c = (_by_name(db, name) for name in ("ЖК «Северный бриз»", "ЖК «Золотая осень»", "ЖК «Тихая гавань»"))
    assert "Сценарий A" in a.aliases and "Сценарий B" in b.aliases and "Сценарий C" in c.aliases

    def permits(obj: ConstructionObject) -> dict[DocType, CheckStatus]:
        rows = db.scalars(
            select(Document).where(
                Document.object_id == obj.id, Document.doc_type.in_([DocType.guarantee, DocType.dsu_permit])
            )
        )
        return {row.doc_type: row.check_status for row in rows}

    assert permits(a) == {}  # A: the basis was never checked
    assert permits(b) == {DocType.guarantee: CheckStatus.not_found, DocType.dsu_permit: CheckStatus.not_found}
    assert permits(c) == {DocType.guarantee: CheckStatus.confirmed}  # C: no separate MIO permit

    for obj in (a, b, c):
        for ad in _ads(db, obj):
            analyze_ad(db, ad)
    [paid_booking] = _ads(db, a)
    assert "Платная бронь" in (paid_booking.text or "")
    assert PhraseCategory.booking in _hit_categories(db, paid_booking)
    deposit = _ads(db, b)[0]
    assert "Внесите депозит" in (deposit.text or "")
    assert PhraseCategory.deposit in _hit_categories(db, deposit)
    [ordinary] = _ads(db, c)
    assert _hit_categories(db, ordinary) == set()


def test_every_risky_text_is_matched_by_the_dictionary(db: Session, demo: list[int]) -> None:
    """The texts were written to contain wording the seeded dictionary matches, not only declared schemes."""
    risky_categories = {
        "ЖК «Северный бриз»": PhraseCategory.booking,
        "ЖК «Золотая осень»": PhraseCategory.deposit,
        "ЖК «Кедровый квартал»": PhraseCategory.installment,
        "ЖК «Лазурный берег»": PhraseCategory.installment,
    }
    for name, category in risky_categories.items():
        found: set[PhraseCategory] = set()
        for ad in _ads(db, _by_name(db, name)):
            analyze_ad(db, ad)
            found |= _hit_categories(db, ad)
        assert category in found, name
    for ad in _ads(db, _by_name(db, "ЖК «Хрустальный город»")):
        analyze_ad(db, ad)
        assert PhraseCategory.covert_contract in _hit_categories(db, ad), ad.external_id  # every one of the three


def test_complaints_carry_the_verification_the_case_needs(db: Session, demo: list[int]) -> None:
    [verified] = db.scalars(select(Complaint).where(Complaint.external_id == "EO-DEMO-0103"))
    assert verified.is_collective and verified.is_verified and verified.verified_by is not None
    assert verified.verified_at is not None
    [unverified] = db.scalars(select(Complaint).where(Complaint.external_id == "DEMO-C-0105"))
    assert unverified.is_collective and not unverified.is_verified and unverified.verified_by is None


def test_checked_documents_name_the_demo_officer(db: Session, demo: list[int]) -> None:
    checked = list(
        db.scalars(
            select(Document).where(Document.check_status != CheckStatus.checking, Document.check_source.is_not(None))
        )
    )
    assert checked and all(row.checked_by is not None for row in checked)
    pending = list(db.scalars(select(Document).where(Document.check_status == CheckStatus.checking)))
    assert pending and all(row.checked_by is None and row.checked_at is None for row in pending)


def test_scores_and_zones_follow_the_case_model(db: Session, demo: list[int]) -> None:
    for ad in db.scalars(select(AdPost)):
        analyze_ad(db, ad)  # what the nlp.analyze task does for every demo ad
    result: dict[str, Any] = {}
    for object_id in demo:
        recalculate(db, object_id, ScoreTrigger.manual)
        obj = db.get(ConstructionObject, object_id)
        assert obj is not None and obj.zone is not None and obj.score is not None
        result[obj.name] = (obj.score, obj.zone)
    assert result == EXPECTED
    zones = [zone for _, zone in result.values()]
    assert (zones.count(Zone.green), zones.count(Zone.yellow), zones.count(Zone.red)) == (9, 5, 2)


class _Recorder:
    def __init__(self) -> None:
        self.chains: list[list[tuple[str, tuple[Any, ...], str | None]]] = []

    def chain(self, *signatures: Any) -> Any:
        recorded = [(sig.task, tuple(sig.args), sig.options.get("queue")) for sig in signatures]
        recorder = self

        class _Chain:
            def apply_async(self, **kwargs: Any) -> None:
                recorder.chains.append(recorded)

        return _Chain()


def test_loaded_ads_go_through_nlp_before_their_object_is_rescored(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    rescored: list[list[int]] = []
    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr(seed, "chain", recorder.chain)
    monkeypatch.setattr(seed, "objects_changed", lambda ids: rescored.append(list(ids)))

    seed.dispatch_demo_processing([(11, 1), (12, 1), (13, 2)], objects_without_ads=[3, 4])

    assert recorder.chains[0] == [
        ("nlp.analyze", (11,), "nlp"),
        ("nlp.link", (11,), "nlp"),
        ("risk.recalc_object", (1,), "score"),
    ]
    assert [chain[0][1] for chain in recorder.chains] == [(11,), (12,), (13,)]
    assert rescored == [[3, 4]]


def test_nothing_is_queued_while_events_are_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("broker must not be used")

    monkeypatch.setattr(seed, "chain", fail)
    monkeypatch.setattr(seed, "objects_changed", fail)
    seed.dispatch_demo_processing([(1, 1)], objects_without_ads=[2])  # EVENTS_ENABLED=false in tests

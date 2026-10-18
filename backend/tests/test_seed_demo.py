import itertools
import json
import math
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import seed, seed_history
from app.config import get_settings
from app.models import AdPost, Complaint, ConstructionObject, Developer, District, Document, PhraseHit, RiskScore
from app.models.enums import CheckStatus, DocType, PhraseCategory, ScoreTrigger, Zone
from app.modules.graph.service import build_graph
from app.modules.graph.suggestions import list_suggestions
from app.modules.nlp.service import analyze_ad
from app.modules.risk.queries import latest_score_stmt
from app.modules.risk.service import recalculate
from app.scope import TerritoryScope

DEMO_FILE = seed.SEED_DATA_DIR / "demo_objects.json"
DEMO = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
NETWORK = json.loads((seed.SEED_DATA_DIR / seed.DEMO_NETWORK_FILE).read_text(encoding="utf-8"))

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


# The story "one phone for three" (SPEC 10.3): a red, a yellow and a green object of three developers.
NETWORK_EXPECTED: dict[str, tuple[int, Zone]] = {
    "ЖК «Ривьера Парк»": (70, Zone.red),  # no legal basis established + a deposit
    "ЖК «Меридиан Сити»": (35, Zone.yellow),  # confirmed guarantee, but an installment offer
    "ЖК «Сосновый бор»": (10, Zone.green),  # confirmed guarantee + ordinary advertising
}
NETWORK_PHONE = "+77000002001"
NETWORK_ACCOUNT = "instagram/prime_estate_demo"


@pytest.fixture
def demo(db: Session) -> list[int]:
    seed.seed_reference(db)
    seed.load_districts(db)
    seed.seed_demo_users(db)
    return seed.seed_demo_objects(db)


@pytest.fixture
def network(db: Session, demo: list[int]) -> list[int]:
    """The network loaded after the control scenarios, as `python -m app.seed --demo` does."""
    return seed.seed_demo_objects(db, seed.DEMO_NETWORK_FILE)


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
    monkeypatch.setattr(get_settings(), "llm_enabled", False)
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


def test_llm_extraction_joins_the_chain_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr(get_settings(), "llm_enabled", True)
    monkeypatch.setattr(seed, "chain", recorder.chain)
    monkeypatch.setattr(seed, "objects_changed", lambda ids: None)

    seed.dispatch_demo_processing([(11, 1)], objects_without_ads=[])

    assert [step[0] for step in recorder.chains[0]] == [
        "nlp.analyze",
        "nlp.link",
        "nlp.llm_extract",
        "risk.recalc_object",
    ]


def test_nothing_is_queued_while_events_are_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("broker must not be used")

    monkeypatch.setattr(seed, "chain", fail)
    monkeypatch.setattr(seed, "objects_changed", fail)
    seed.dispatch_demo_processing([(1, 1)], objects_without_ads=[2])  # EVENTS_ENABLED=false in tests


def _score_everything(db: Session, object_ids: list[int]) -> dict[str, tuple[int, Zone]]:
    for ad in db.scalars(select(AdPost)):
        analyze_ad(db, ad)
    result: dict[str, tuple[int, Zone]] = {}
    for object_id in object_ids:
        recalculate(db, object_id, ScoreTrigger.manual)
        obj = db.get(ConstructionObject, object_id)
        assert obj is not None and obj.zone is not None and obj.score is not None
        result[obj.name] = (obj.score, obj.zone)
    return result


def test_network_file_is_fictional_and_isolated_from_the_other_demo_data() -> None:
    assert len(NETWORK["developers"]) == len(NETWORK["objects"]) == 3
    own_phones: set[str] = set()
    for developer in NETWORK["developers"]:
        assert re.fullmatch(r"99[0-9]{10}", developer["bin"]), "fictional BINs start with 99"
        assert all(re.fullmatch(r"\+7 700 000 \d\d \d\d", phone) for phone in developer["phones"])
        own_phones.update(developer["phones"])
    ads = [ad for obj in NETWORK["objects"] for ad in obj["ads"]]
    for obj in NETWORK["objects"]:
        assert obj["documents"] and obj["inspections"] and obj["linked_entities"] and obj["developer_bin"]
        for entity in obj["linked_entities"]:
            assert entity["kind"] != "phone" or re.fullmatch(r"\+7700000\d{4}", entity["value"])
            if entity["kind"] == "phone":
                own_phones.add(entity["value"])
    for ad in ads:
        assert ad["url"] is None or ad["url"].startswith("https://example.invalid/")
        assert re.fullmatch(r"-([1-9]|1\d|20)d", ad["published_at"])
        assert re.search(r"\+7 700 000 \d\d \d\d", ad["text"])
    assert len(ads) >= 3

    existing_phones = {phone.replace(" ", "") for developer in DEMO["developers"] for phone in developer["phones"]}
    existing_phones |= {entity["value"] for obj in DEMO["objects"] for entity in obj["linked_entities"]}
    existing_phones |= {
        phone.replace(" ", "") for obj in DEMO["objects"] for ad in obj["ads"] for phone in ad["phones"]
    }
    assert not {phone.replace(" ", "") for phone in own_phones} & existing_phones
    assert {developer["bin"] for developer in NETWORK["developers"]}.isdisjoint(
        developer["bin"] for developer in DEMO["developers"]
    )
    assert {obj["name"] for obj in NETWORK["objects"]}.isdisjoint(obj["name"] for obj in DEMO["objects"])
    assert {obj["cadastral_number"] for obj in NETWORK["objects"]}.isdisjoint(
        obj["cadastral_number"] for obj in DEMO["objects"]
    )


def test_network_is_marked_as_demo_and_loaded_once(db: Session, demo: list[int], network: list[int]) -> None:
    assert len(network) == 3 and not set(network) & set(demo)
    assert (
        db.scalar(select(func.count()).select_from(ConstructionObject).where(ConstructionObject.is_demo.is_(False)))
        == 0
    )
    assert db.scalar(select(func.count()).select_from(AdPost).where(AdPost.is_demo.is_(False))) == 0
    assert seed.seed_demo_objects(db, seed.DEMO_NETWORK_FILE) == []
    assert db.scalar(select(func.count()).select_from(Developer)) == len(DEMO["developers"]) + 3
    for obj in db.scalars(select(ConstructionObject).where(ConstructionObject.id.in_(network))):
        assert obj.district_id is not None, obj.name  # every point lies inside a district


def test_network_objects_stay_away_from_the_other_demo_objects() -> None:
    def kilometres(a: dict[str, Any], b: dict[str, Any]) -> float:
        return math.hypot(
            (a["lat"] - b["lat"]) * 111.2, (a["lon"] - b["lon"]) * 111.2 * math.cos(math.radians(a["lat"]))
        )

    for new in NETWORK["objects"]:
        assert min(kilometres(new, old) for old in DEMO["objects"]) > 1.0, new["name"]


def test_network_changes_no_control_scenario_and_no_other_demo_score(
    db: Session, demo: list[int], network: list[int]
) -> None:
    result = _score_everything(db, [*demo, *network])

    assert {name: result[name] for name in EXPECTED} == EXPECTED
    assert result["ЖК «Северный бриз»"] == (35, Zone.yellow)  # scenario A
    assert result["ЖК «Золотая осень»"] == (70, Zone.red)  # scenario B
    assert result["ЖК «Тихая гавань»"] == (10, Zone.green)  # scenario C
    assert {name: result[name] for name in NETWORK_EXPECTED} == NETWORK_EXPECTED
    zones = [result[name][1] for name in EXPECTED]
    assert (zones.count(Zone.green), zones.count(Zone.yellow), zones.count(Zone.red)) == (9, 5, 2)


def test_network_ads_belong_to_the_network_objects_only(db: Session, demo: list[int], network: list[int]) -> None:
    network_ads = list(db.scalars(select(AdPost).where(AdPost.object_id.in_(network))))
    assert len(network_ads) == sum(len(obj["ads"]) for obj in NETWORK["objects"])
    assert db.scalar(select(func.count()).select_from(AdPost)) == len(network_ads) + sum(
        len(obj["ads"]) for obj in DEMO["objects"]
    )
    for ad in network_ads:
        analyze_ad(db, ad)
        assert ad.phones == [NETWORK_PHONE] and ad.links == ["https://instagram.com/prime_estate_demo"]
    for ad in db.scalars(select(AdPost).where(AdPost.object_id.in_(demo))):
        analyze_ad(db, ad)
        assert NETWORK_PHONE not in ad.phones and not any("prime_estate_demo" in link for link in ad.links)


def test_one_phone_and_one_account_tie_the_three_developers(db: Session, demo: list[int], network: list[int]) -> None:
    new_developers = sorted(
        db.scalars(select(Developer.id).where(Developer.bin.in_([d["bin"] for d in NETWORK["developers"]])))
    )

    # Straight after loading: the phone is on all three cards, the account on two of them.
    findings = {finding.value: finding for finding in build_graph(db, TerritoryScope(ids=None)).findings}
    assert set(findings) == {NETWORK_PHONE, NETWORK_ACCOUNT}
    phone = findings[NETWORK_PHONE]
    assert phone.kind == "shared_phone" and phone.label == "Один телефон у 3 застройщиков"
    assert phone.developer_ids == new_developers and phone.object_ids == sorted(network)
    assert len(findings[NETWORK_ACCOUNT].developer_ids) == 2

    # After nlp.analyze reads the links of the texts, the third object's advertising names the account too.
    for ad in db.scalars(select(AdPost)):
        analyze_ad(db, ad)
    findings = {finding.value: finding for finding in build_graph(db, TerritoryScope(ids=None)).findings}
    assert set(findings) == {NETWORK_PHONE, NETWORK_ACCOUNT}  # nothing else of the demo is a finding
    account = findings[NETWORK_ACCOUNT]
    assert account.kind == "shared_account" and account.label == "Один аккаунт у 3 застройщиков"
    for finding in findings.values():
        assert finding.developer_ids == new_developers and finding.object_ids == sorted(network)


def test_the_network_account_is_offered_as_a_source_candidate(db: Session, demo: list[int], network: list[int]) -> None:
    for ad in db.scalars(select(AdPost)):
        analyze_ad(db, ad)

    [candidate] = list_suggestions(db, TerritoryScope(ids=None))

    assert (candidate.platform, candidate.handle) == ("instagram", "prime_estate_demo")
    assert candidate.posts_count == sum(len(obj["ads"]) for obj in NETWORK["objects"])
    assert candidate.object_ids == sorted(network)


# ---------------------------------------------------------------- dated history for the time machine (SPEC 10.5)

HISTORY = json.loads((seed.SEED_DATA_DIR / "demo_history.json").read_text(encoding="utf-8"))
SLICES = seed_history.HISTORY_WEEKS + 1  # weekly, both ends included
GOLDEN_AUTUMN = "ЖК «Золотая осень»"
CRYSTAL_CITY = "ЖК «Хрустальный город»"


@pytest.fixture
def demo_history(db: Session, demo: list[int]) -> list[int]:
    seed_history.seed_demo_history(db, demo)
    return demo


class _Borrowed:
    """Lends the test session to code that opens its own session from a factory."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *exc: object) -> None:
        return None


def _replayed(db: Session, name: str) -> list[RiskScore]:
    obj = _by_name(db, name)
    return list(
        db.scalars(
            select(RiskScore)
            .where(RiskScore.object_id == obj.id, RiskScore.trigger == ScoreTrigger.replay)
            .order_by(RiskScore.calculated_at)
        )
    )


def _zone_path(rows: list[RiskScore]) -> list[Zone]:
    """The zones in order of time, consecutive repeats collapsed."""
    path: list[Zone] = []
    for row in rows:
        if not path or path[-1] is not row.zone:
            path.append(row.zone)
    return path


def _fired(row: RiskScore) -> set[str]:
    return {factor["code"] for factor in row.breakdown["factors"] if factor["triggered"]}


def _without_complaint_count(breakdown: dict[str, Any]) -> dict[str, Any]:
    """The breakdown minus the one detail that history is meant to change: how many complaints are on file."""
    factors = [
        {**factor, "detail": {k: v for k, v in factor["detail"].items() if k != "count"}}
        if factor["code"] == "r4_collective_complaint"
        else factor
        for factor in breakdown["factors"]
    ]
    return {**breakdown, "factors": factors}


def test_history_file_is_fictional_dated_in_the_past_and_outside_the_analysis_window() -> None:
    names = {obj["name"] for obj in DEMO["objects"]}
    ads = [ad for item in HISTORY["objects"] for ad in item.get("ads", [])]
    assert {item["name"] for item in HISTORY["objects"]} <= names and len(ads) >= 20
    for ad in ads:
        assert ad["url"].startswith("https://example.invalid/") and ad["external_id"].startswith("demo-hist-")
        assert re.search(r"\+7 700 000 \d\d \d\d", ad["text"])
        match = re.fullmatch(r"-(\d+)d", ad["published_at"])
        assert match is not None and 32 <= int(match[1]) <= 175, "1-6 months back, outside the 30-day window"
    assert len({ad["external_id"] for ad in ads}) == len(ads)
    # An older ad names its own object's phone: a phone of another card would tie two developers in the link graph.
    own_phones = {
        obj["name"]: {entity["value"] for entity in obj["linked_entities"] if entity["kind"] == "phone"}
        for obj in DEMO["objects"]
    }
    for item in HISTORY["objects"]:
        for ad in item.get("ads", []):
            assert {phone.replace(" ", "") for phone in ad["phones"]} <= own_phones[item["name"]], ad["external_id"]
    for item in HISTORY["objects"]:
        dates = [fact["checked_at"] for fact in item.get("document_checks", [])]
        dates += [fact["verified_at"] for fact in item.get("complaint_verifications", [])]
        dates += [complaint["received_at"] for complaint in item.get("complaints", [])]
        assert all(re.fullmatch(r"-\d+d", date) for date in dates)


def test_history_leaves_every_current_breakdown_as_it_was(db: Session, demo: list[int]) -> None:
    for ad in db.scalars(select(AdPost)):
        analyze_ad(db, ad)
    before = {}
    for object_id in demo:
        result = recalculate(db, object_id, ScoreTrigger.manual)
        assert result is not None
        before[object_id] = _without_complaint_count(result.risk_score.breakdown)

    seed_history.seed_demo_history(db, demo)

    scores: dict[str, tuple[int, Zone]] = {}
    for object_id in demo:
        result = recalculate(db, object_id, ScoreTrigger.manual)
        assert result is not None
        assert _without_complaint_count(result.risk_score.breakdown) == before[object_id]  # evidence and flags too
        scores[db.get_one(ConstructionObject, object_id).name] = (result.risk_score.score, result.risk_score.zone)
    assert scores == EXPECTED

    def factors(name: str) -> tuple[set[str], str]:
        row = db.scalar(latest_score_stmt(_by_name(db, name).id))
        assert row is not None and row.trigger is ScoreTrigger.manual
        return _fired(row), row.breakdown["legal_basis_status"]

    assert factors("ЖК «Северный бриз»") == ({"r2_money_offer", "r3_active_ads"}, "unknown")  # A
    assert factors(GOLDEN_AUTUMN) == (
        {"r1_no_legal_basis", "r2_money_offer", "r3_active_ads"},
        "absent_established",
    )  # B
    assert factors("ЖК «Тихая гавань»") == ({"r3_active_ads"}, "confirmed")  # C


def test_older_check_dates_do_not_change_what_the_documents_say(db: Session, demo: list[int]) -> None:
    def documents() -> dict[tuple[int, DocType], Document]:
        return {(row.object_id, row.doc_type): row for row in db.scalars(select(Document))}

    before = {key: (row.check_status, row.checked_at) for key, row in documents().items()}
    seed_history.seed_demo_history(db, demo)
    after = {key: (row.check_status, row.checked_at) for key, row in documents().items()}

    assert {key: value[0] for key, value in after.items()} == {key: value[0] for key, value in before.items()}
    moved = {key for key in before if before[key][1] != after[key][1]}
    names = {object_id: db.get_one(ConstructionObject, object_id).name for object_id, _ in moved}
    assert {(names[object_id], doc_type) for object_id, doc_type in moved} == {
        (GOLDEN_AUTUMN, DocType.guarantee),
        (GOLDEN_AUTUMN, DocType.dsu_permit),
        (CRYSTAL_CITY, DocType.guarantee),
        (CRYSTAL_CITY, DocType.dsu_permit),
    }
    for key in moved:
        earlier, later = after[key][1], before[key][1]
        assert earlier is not None and later is not None and earlier < later


def test_every_demo_object_gets_a_weekly_replayed_history_that_ends_before_the_real_score(
    db: Session, demo_history: list[int]
) -> None:
    for object_id in demo_history:
        obj = db.get_one(ConstructionObject, object_id)
        rows = _replayed(db, obj.name)
        assert len(rows) == SLICES, obj.name
        assert {row.trigger for row in rows} == {ScoreTrigger.replay}
        assert {b.calculated_at - a.calculated_at for a, b in itertools.pairwise(rows)} == {timedelta(weeks=1)}
        assert rows[-1].calculated_at <= datetime.now(UTC)
        assert (obj.score, obj.zone, obj.last_scored_at) == (None, None, None)  # a replay is not a scoring

    real = recalculate(db, demo_history[0], ScoreTrigger.manual)
    assert real is not None
    assert db.scalar(latest_score_stmt(demo_history[0])) == real.risk_score


def test_golden_autumn_goes_green_yellow_red_as_its_facts_appear(db: Session, demo_history: list[int]) -> None:
    rows = _replayed(db, GOLDEN_AUTUMN)
    assert _zone_path(rows) == [Zone.green, Zone.yellow, Zone.red]

    yellow = [row for row in rows if row.zone is Zone.yellow]
    red = [row for row in rows if row.zone is Zone.red]
    # Yellow: an offer of money while the basis is unchecked. Red: only from the day both checks had been made.
    assert all(_fired(row) == {"r2_money_offer", "r3_active_ads"} for row in yellow)
    assert all(_fired(row) == {"r1_no_legal_basis", "r2_money_offer", "r3_active_ads"} for row in red)
    checks = [
        row.checked_at
        for row in db.scalars(select(Document).where(Document.object_id == _by_name(db, GOLDEN_AUTUMN).id))
        if row.checked_at is not None
    ]
    assert rows[rows.index(red[0]) - 1].calculated_at < max(checks) <= red[0].calculated_at
    assert (red[-1].score, red[-1].zone) == (70, Zone.red)  # the last slice meets the present state
    assert len(yellow) >= 2 and len(red) >= 6


def test_northern_breeze_is_yellow_for_weeks(db: Session, demo_history: list[int]) -> None:
    rows = _replayed(db, "ЖК «Северный бриз»")
    assert _zone_path(rows) == [Zone.green, Zone.yellow]
    assert sum(row.zone is Zone.yellow for row in rows) >= 10
    assert {row.breakdown["legal_basis_status"] for row in rows} == {"unknown"}  # it never was a finding of absence


def test_quiet_harbor_is_mostly_green(db: Session, demo_history: list[int]) -> None:
    rows = _replayed(db, "ЖК «Тихая гавань»")
    assert Zone.red not in {row.zone for row in rows}
    assert sum(row.zone is Zone.green for row in rows) >= 0.8 * len(rows)
    assert rows[-1].zone is Zone.green


def test_poplar_alley_turns_yellow_only_after_the_complaint_was_verified(db: Session, demo_history: list[int]) -> None:
    rows = _replayed(db, "ЖК «Тополиная аллея»")
    [complaint] = db.scalars(select(Complaint).where(Complaint.external_id == "EO-DEMO-0103"))
    assert complaint.verified_at is not None and complaint.verified_at < datetime.now(UTC) - timedelta(days=20)

    assert _zone_path(rows) == [Zone.green, Zone.yellow]
    first_yellow = next(index for index, row in enumerate(rows) if row.zone is Zone.yellow)
    assert rows[first_yellow - 1].calculated_at < complaint.verified_at <= rows[first_yellow].calculated_at
    assert "r4_collective_complaint" in _fired(rows[first_yellow])
    assert "complaint_unverified" in {flag["code"] for flag in rows[first_yellow - 1].breakdown["needs_check"]}


def test_crystal_city_goes_green_yellow_red(db: Session, demo_history: list[int]) -> None:
    assert _zone_path(_replayed(db, CRYSTAL_CITY)) == [Zone.green, Zone.yellow, Zone.red]


def test_repeating_the_history_adds_neither_facts_nor_slices(db: Session, demo_history: list[int]) -> None:
    ads = db.scalar(select(func.count()).select_from(AdPost))
    complaints = db.scalar(select(func.count()).select_from(Complaint))

    assert seed_history.seed_demo_history(db, demo_history) == len(demo_history) * SLICES

    assert db.scalar(select(func.count()).select_from(AdPost)) == ads
    assert db.scalar(select(func.count()).select_from(Complaint)) == complaints
    assert db.scalar(select(func.count()).select_from(RiskScore)) == len(demo_history) * SLICES


def test_a_history_file_that_dates_a_missing_document_is_rejected(
    db: Session, demo: list[int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = {
        "objects": [
            {"name": "ЖК «Северный бриз»", "document_checks": [{"doc_type": "guarantee", "checked_at": "-40d"}]}
        ]
    }
    (tmp_path / "demo_history.json").write_text(json.dumps(broken))  # the object has no guarantee document
    monkeypatch.setattr(seed_history, "SEED_DATA_DIR", tmp_path)
    with pytest.raises(SystemExit, match="guarantee"):
        seed_history.seed_demo_history(db, demo)


def test_replay_history_flag_recomputes_the_history_of_every_object(
    db: Session, demo_history: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: lambda: _Borrowed(db))
    db.execute(delete(RiskScore))
    db.add(ConstructionObject(territory_id=_by_name(db, GOLDEN_AUTUMN).territory_id, name="ЖК Не из демо"))
    db.flush()

    seed.main(["--replay-history"])

    assert db.scalar(select(func.count()).select_from(RiskScore)) == (len(demo_history) + 1) * SLICES
    assert _zone_path(_replayed(db, GOLDEN_AUTUMN)) == [Zone.green, Zone.yellow, Zone.red]


def test_demo_loading_stores_the_replayed_history(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: lambda: _Borrowed(db))

    seed.run(demo=True)

    # Every demo object gets its replayed slices: those of demo_objects.json, of the network story and the one of
    # the versions story.
    demo_objects = db.scalar(
        select(func.count()).select_from(ConstructionObject).where(ConstructionObject.is_demo.is_(True))
    )
    assert demo_objects == len(DEMO["objects"]) + len(NETWORK["objects"]) + 1
    replayed = select(func.count()).select_from(RiskScore).where(RiskScore.trigger == ScoreTrigger.replay)
    assert db.scalar(replayed) == demo_objects * SLICES
    history_ads = db.scalar(select(func.count()).select_from(AdPost).where(AdPost.external_id.like("demo-hist-%")))
    assert history_ads == sum(len(item.get("ads", [])) for item in HISTORY["objects"])

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from asn1crypto import algos, cms, tsp
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import seed, storage
from app.config import get_settings
from app.events import object_changed
from app.models import AppSetting, ConstructionObject, Document, Holiday, Phrase, RiskFactor, Territory
from app.models.enums import DocType, EvidenceKind, PhraseCategory
from app.storage import EvidenceLink
from tests.conftest import PNG_BYTES, World, make_object


def test_seed_reference_is_idempotent_and_matches_spec(db: Session) -> None:
    seed.seed_reference(db)
    seed.seed_reference(db)
    factors = {f.code: f.weight for f in db.scalars(select(RiskFactor))}
    assert factors == {
        "no_permit": 40,
        "money_offer": 20,
        "active_ads": 15,
        "complaints": 15,
        "readiness_overstated": 10,
        "on_schedule": -15,
    }
    phrases = db.scalars(select(Phrase)).all()
    assert len(phrases) == 9
    assert {p.category for p in phrases} == set(PhraseCategory)
    assert {p.weight for p in phrases if p.category is PhraseCategory.covert_contract} == {12}
    assert db.scalar(select(func.count()).select_from(AppSetting)) == 10
    city = db.scalars(select(Territory).where(Territory.code == "ust-kamenogorsk")).one()
    assert city.timezone == "Asia/Almaty" and city.parent_id is not None


def test_seed_keeps_admin_edits(db: Session) -> None:
    seed.seed_reference(db)
    factor = db.get(RiskFactor, "no_permit")
    assert factor is not None
    factor.weight = 55
    db.flush()
    seed.seed_reference(db)
    assert db.get(RiskFactor, "no_permit").weight == 55  # type: ignore[union-attr]


def test_seed_demo_users_and_objects(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed.seed_reference(db)
    (tmp_path / "demo_objects.json").write_text(
        json.dumps(
            {
                "developers": [{"bin": "999999999999", "name": "ТОО Вымышленный", "phones": ["+7 701 000 00 01"]}],
                "objects": [
                    {
                        "name": "ЖК Вымышленный",
                        "developer_bin": "999999999999",
                        "lat": 49.95,
                        "lon": 82.6,
                        "inspections": [
                            {"inspected_at": "2026-05-01", "readiness_pct": 20},
                            {"inspected_at": "2026-08-01", "readiness_pct": 35},
                        ],
                        "documents": [{"doc_type": "dsu_permit", "check_status": "not_found"}],
                        "complaints": [{"received_at": "2026-09-01", "is_collective": True}],
                        "linked_entities": [{"kind": "phone", "value": "+77010000001"}],
                        "ads": [
                            {
                                "platform": "instagram",
                                "published_at": "2026-10-01T10:00:00+05:00",
                                "text": "Бронь квартир открыта",
                                "phones": ["8 701 000 00 01"],
                                "claimed_readiness_pct": 60,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(seed, "SEED_DATA_DIR", tmp_path)
    monkeypatch.setattr(get_settings(), "demo_user_password", "demo-password-1")

    credentials = seed.seed_demo_users(db)
    assert {name for name, _ in credentials} == {"demo_admin", "demo_mio", "demo_gask", "demo_police"}
    assert seed.seed_demo_users(db) == []

    created = seed.seed_demo_objects(db)
    assert len(created) == 1
    assert seed.seed_demo_objects(db) == []
    obj = db.get(ConstructionObject, created[0])
    assert obj is not None and obj.is_demo
    assert obj.readiness_actual_pct == 35 and obj.readiness_claimed_pct == 60


def test_seed_loads_districts_and_holidays(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed.seed_reference(db)
    polygon = {"type": "Polygon", "coordinates": [[[82, 49], [83, 49], [83, 50], [82, 50], [82, 49]]]}
    (tmp_path / "districts.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {"name": "Тестовый"}, "geometry": polygon}],
            }
        )
    )
    (tmp_path / "holidays.json").write_text(
        json.dumps([{"day": "2026-12-16", "kind": "holiday", "name": "День Независимости"}])
    )
    monkeypatch.setattr(seed, "SEED_DATA_DIR", tmp_path)
    assert seed.load_districts(db) == 1 and seed.load_districts(db) == 1
    assert seed.load_holidays(db) == 1
    assert db.scalar(select(func.count()).select_from(Holiday)) == 1


def test_object_changed_sends_risk_task_by_name(sent_tasks: list) -> None:
    object_changed(42)
    assert sent_tasks == [("risk.recalc_object", (42,))]


def test_object_changed_is_noop_when_events_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("broker must not be used")

    monkeypatch.setattr("app.events.celery_app.send_task", boom)
    object_changed(1)  # EVENTS_ENABLED=false in tests


def test_object_changed_survives_broker_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr(get_settings(), "events_enabled", True)
    monkeypatch.setattr("app.events.celery_app.send_task", broken)
    object_changed(7)
    assert "risk.recalc_object" in caplog.text


def test_celery_registers_contract_tasks_and_schedule() -> None:
    from app.worker.celery_app import celery_app

    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert scheduled == {"collect.run_all", "risk.sweep_due", "ads.recheck_due", "signals.check_deadlines"}
    routed = set(celery_app.conf.task_routes)
    assert routed == {
        "archive.capture", "nlp.analyze", "nlp.link", "nlp.llm_extract", "ads.recheck_due",
        "collect.run_all", "risk.recalc_object", "risk.sweep_due", "signals.check_deadlines", "notify.red_zone",
    }  # fmt: skip
    assert {queue.name for queue in celery_app.conf.task_queues} == {
        "collect",
        "archive",
        "nlp",
        "score",
        "notify",
        "default",
    }
    # Each queue needs its own exchange/key, otherwise every message lands in every queue.
    assert all(q.exchange.name == q.name == q.routing_key for q in celery_app.conf.task_queues)


def test_evidence_link_requires_exactly_one_owner() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        EvidenceLink().owner()
    with pytest.raises(ValueError, match="exactly one"):
        EvidenceLink(document_id=1, inspection_id=2).owner()
    assert EvidenceLink(ad_post_id=5).owner() == ("ad_post_id", 5)


def _document(db: Session, world: World) -> Document:
    document = Document(object_id=make_object(db, world.ust).id, doc_type=DocType.psd)
    db.add(document)
    db.flush()
    return document


def test_tsa_failure_does_not_fail_capture(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "tsa_url", "http://127.0.0.1:9/tsa")  # nothing listens there
    document = _document(db, world)
    evidence = storage.put_evidence(
        db, PNG_BYTES, EvidenceKind.document_scan, "image/png", link=EvidenceLink(document_id=document.id)
    )
    assert evidence.tsa_token is None
    assert evidence.sha256 and evidence.id


def _fake_tsa_response(request_body: bytes) -> bytes:
    request = tsp.TimeStampReq.load(request_body)
    info = tsp.TSTInfo(
        {
            "version": "v1",
            "policy": "1.2.3.4",
            "message_imprint": request["message_imprint"],
            "serial_number": 1,
            "gen_time": datetime.now(UTC),
            "nonce": request["nonce"],
        }
    )
    signed = cms.SignedData(
        {
            "version": "v3",
            "digest_algorithms": [algos.DigestAlgorithm({"algorithm": "sha256"})],
            "encap_content_info": {"content_type": "tst_info", "content": info},
            "signer_infos": [],
        }
    )
    token = cms.ContentInfo({"content_type": "signed_data", "content": signed})
    return bytes(tsp.TimeStampResp({"status": {"status": "granted"}, "time_stamp_token": token}).dump())


def test_tsa_token_is_requested_over_sha256_only_and_stored(
    db: Session, world: World, bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bytes] = []

    def fake_post(url: str, *, content: bytes, headers: dict, timeout: float) -> httpx.Response:
        seen.append(content)
        assert headers["Content-Type"] == "application/timestamp-query"
        return httpx.Response(200, content=_fake_tsa_response(content), request=httpx.Request("POST", url))

    monkeypatch.setattr(get_settings(), "tsa_url", "http://tsa.invalid/")
    monkeypatch.setattr("app.storage.httpx.post", fake_post)
    document = _document(db, world)
    evidence = storage.put_evidence(
        db, PNG_BYTES, EvidenceKind.document_scan, "image/png", link=EvidenceLink(document_id=document.id)
    )

    assert evidence.tsa_token is not None
    imprint = tsp.TimeStampReq.load(seen[0])["message_imprint"]["hashed_message"].native
    assert imprint.hex() == evidence.sha256
    assert PNG_BYTES not in seen[0]  # only the digest leaves the system


def test_tsa_mismatched_response_is_discarded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.storage.httpx.post",
        lambda url, **kwargs: httpx.Response(200, content=b"not asn1", request=httpx.Request("POST", url)),
    )
    assert storage.request_timestamp(b"\x00" * 32, "http://tsa.invalid/") is None


def test_collector_registry() -> None:
    from datetime import datetime

    from app.collectors import base
    from app.models.enums import Platform

    class FakeCollector:
        platform = Platform.telegram

        def collect(self, account: object, since: datetime) -> list[base.CollectedPost]:
            return [base.CollectedPost(external_id="1", text="пост")]

    base._registry.clear()
    try:
        assert base.get_collector(Platform.telegram) is None
        base.register(FakeCollector())
        assert base.registered_platforms() == [Platform.telegram]
        assert base.get_collector(Platform.telegram) is not None
        with pytest.raises(ValueError, match="already registered"):
            base.register(FakeCollector())
    finally:
        base._registry.clear()

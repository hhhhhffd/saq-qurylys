"""HTTP API of the risk module: score history, manual recalculation and risk factor weights."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, ConstructionObject, RiskFactor, RiskFactorChange, RiskScore, SignalCard
from app.models.enums import DocType, ScoreTrigger, Zone
from tests.conftest import World, auth, make_object
from tests.support_risk import NOW, add_complaint, add_document, red_object


def _score(db: Session, obj: ConstructionObject, score: int, minutes: int) -> RiskScore:
    row = RiskScore(
        object_id=obj.id,
        score=score,
        zone=Zone.yellow,
        zone_reasons=["no_permit"],
        breakdown=[],
        trigger=ScoreTrigger.event,
        calculated_at=NOW + timedelta(minutes=minutes),
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------- score history


def test_score_history_is_newest_first_and_paged(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    older, newer = _score(db, obj, 10, 0), _score(db, obj, 20, 5)
    _score(db, make_object(db, world.ust, "Другой"), 99, 1)
    headers = auth(world.users["mio_ust"])

    body = client.get(f"/api/v1/objects/{obj.id}/score-history", headers=headers).json()

    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [newer.id, older.id]
    first = body["items"][0]
    assert first["object_id"] == obj.id
    assert {"score", "zone", "zone_reasons", "breakdown", "trigger", "calculated_at"} <= first.keys()
    page = client.get(f"/api/v1/objects/{obj.id}/score-history?limit=1&offset=1", headers=headers).json()
    assert [item["id"] for item in page["items"]] == [older.id]
    assert page["total"] == 2


def test_score_history_respects_scope_and_role(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    url = f"/api/v1/objects/{obj.id}/score-history"
    assert client.get(url, headers=auth(world.users["mio_semey"])).status_code == 404
    assert client.get(url, headers=auth(world.users["gask"])).status_code == 403
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth(world.users["admin"])).status_code == 200


# ---------------------------------------------------------------- recalculate


def test_manual_recalculation_scores_the_object(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_complaint(db, obj)
    headers = auth(world.users["mio_ust"])

    response = client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["score"], body["zone"], body["trigger"]) == (40, "yellow", "manual")
    assert body["zone_reasons"] == ["no_permit"]
    assert {item["code"] for item in body["breakdown"]} >= {"no_permit", "complaints"}
    detail = client.get(f"/api/v1/objects/{obj.id}", headers=headers).json()
    assert detail["latest_score"]["calculated_at"] == body["calculated_at"]
    assert (detail["score"], detail["zone"], detail["key_status"]) == (40, "yellow", "no_permit")
    assert detail["next_check_at"] is not None


def test_manual_recalculation_of_a_red_object_drafts_a_card_and_queues_the_notification(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    obj = red_object(db, world.ust)
    headers = auth(world.users["mio_ust"])

    assert client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=headers).json()["zone"] == "red"
    assert ("notify.red_zone", (obj.id,)) in sent_tasks
    assert len(db.scalars(select(SignalCard).where(SignalCard.object_id == obj.id)).all()) == 1

    sent_tasks.clear()
    client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=headers)
    assert sent_tasks == []
    assert len(db.scalars(select(SignalCard).where(SignalCard.object_id == obj.id)).all()) == 1


def test_recalculation_respects_scope_and_role(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    url = f"/api/v1/objects/{obj.id}/recalculate"
    assert client.post(url, headers=auth(world.users["mio_semey"])).status_code == 404
    assert client.post(url, headers=auth(world.users["gask"])).status_code == 403
    assert client.post("/api/v1/objects/999999/recalculate", headers=auth(world.users["admin"])).status_code == 404
    assert client.post(url, headers=auth(world.users["admin"])).status_code == 200


# ---------------------------------------------------------------- risk factors


def test_risk_factors_are_listed_in_display_order(client: TestClient, world: World) -> None:
    body = client.get("/api/v1/risk-factors", headers=auth(world.users["mio_ust"])).json()
    assert [(item["code"], item["weight"]) for item in body] == [
        ("no_permit", 40),
        ("money_offer", 20),
        ("active_ads", 15),
        ("complaints", 15),
        ("readiness_overstated", 10),
        ("on_schedule", -15),
    ]
    assert body[0].keys() == {"code", "description", "weight", "is_active", "sort_order"}
    assert client.get("/api/v1/risk-factors", headers=auth(world.users["gask"])).status_code == 403


def test_weight_change_is_recorded_and_triggers_a_rescore_of_every_object(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    ust, semey = make_object(db, world.ust), make_object(db, world.semey, "ЖК Семей")
    admin = world.users["admin"]

    response = client.patch("/api/v1/risk-factors/no_permit", headers=auth(admin), json={"weight": 55})

    assert response.status_code == 200, response.text
    assert response.json()["weight"] == 55
    change = db.scalars(select(RiskFactorChange)).one()
    assert (change.code, change.old_weight, change.new_weight) == ("no_permit", 40, 55)
    assert (change.old_active, change.new_active, change.changed_by) == (True, True, admin.id)
    assert {args for name, args in sent_tasks if name == "risk.recalc_object"} >= {(ust.id,), (semey.id,)}
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "risk_factor.update")).one()
    assert entry.before["weight"] == 40 and entry.after["weight"] == 55

    client.post(f"/api/v1/objects/{ust.id}/recalculate", headers=auth(admin))
    assert db.get_one(ConstructionObject, ust.id).score == 55


def test_deactivating_a_factor_is_recorded(client: TestClient, db: Session, world: World) -> None:
    response = client.patch(
        "/api/v1/risk-factors/active_ads", headers=auth(world.users["admin"]), json={"is_active": False}
    )
    assert response.json()["is_active"] is False
    change = db.scalars(select(RiskFactorChange)).one()
    assert (change.old_active, change.new_active, change.old_weight, change.new_weight) == (True, False, 15, 15)


def test_description_only_change_neither_logs_history_nor_rescores(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    make_object(db, world.ust)
    admin = auth(world.users["admin"])
    assert (
        client.patch("/api/v1/risk-factors/no_permit", headers=admin, json={"description": "Новый текст"}).status_code
        == 200
    )
    assert client.patch("/api/v1/risk-factors/no_permit", headers=admin, json={"weight": 40}).status_code == 200
    assert db.get_one(RiskFactor, "no_permit").description == "Новый текст"
    assert db.scalars(select(RiskFactorChange)).all() == []
    assert sent_tasks == []


def test_only_a_global_admin_may_change_weights(client: TestClient, db: Session, world: World) -> None:
    url = "/api/v1/risk-factors/no_permit"
    for role in ("mio_ust", "gask", "admin_semey"):
        assert client.patch(url, headers=auth(world.users[role]), json={"weight": 1}).status_code == 403
    assert client.patch(url, json={"weight": 1}).status_code == 401
    assert db.get_one(RiskFactor, "no_permit").weight == 40


@pytest.mark.parametrize(
    "body", [{"weight": 101}, {"weight": -101}, {"weight": None}, {"is_active": None}, {"description": " "}]
)
def test_invalid_factor_updates_are_rejected(client: TestClient, world: World, body: dict) -> None:
    response = client.patch("/api/v1/risk-factors/no_permit", headers=auth(world.users["admin"]), json=body)
    assert response.status_code == 422


def test_unknown_factor_is_not_found(client: TestClient, world: World) -> None:
    response = client.patch("/api/v1/risk-factors/nope", headers=auth(world.users["admin"]), json={"weight": 5})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "risk_factor_not_found"


def test_factor_history_lists_changes_newest_first_with_the_author(client: TestClient, world: World) -> None:
    admin = auth(world.users["admin"])
    client.patch("/api/v1/risk-factors/no_permit", headers=admin, json={"weight": 50})
    client.patch("/api/v1/risk-factors/money_offer", headers=admin, json={"is_active": False})

    body = client.get("/api/v1/risk-factors/history", headers=auth(world.users["mio_ust"])).json()

    assert body["total"] == 2
    assert [item["code"] for item in body["items"]] == ["money_offer", "no_permit"]
    assert body["items"][1]["old_weight"] == 40 and body["items"][1]["new_weight"] == 50
    assert body["items"][0]["changed_by_name"] == "t_admin"
    assert client.get("/api/v1/risk-factors/history", headers=auth(world.users["gask"])).status_code == 403


def test_zone_stays_rule_based_when_weights_change(client: TestClient, db: Session, world: World) -> None:
    obj = red_object(db, world.ust)
    add_document(db, make_object(db, world.ust, "ЖК Чистый"), DocType.dsu_permit)
    admin = auth(world.users["admin"])
    client.patch("/api/v1/risk-factors/no_permit", headers=admin, json={"weight": -100})
    client.patch("/api/v1/risk-factors/money_offer", headers=admin, json={"weight": -100})
    body = client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=admin).json()
    assert body["score"] == 0  # 15 - 100 - 100, clamped
    assert body["zone"] == "red"

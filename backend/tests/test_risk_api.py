"""HTTP API of the risk module: score history, manual recalculation and risk factor weights."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, ConstructionObject, RiskFactor, RiskFactorChange, RiskScore, SignalCard
from app.models.enums import CheckStatus, DetectedBy, DocType, PhraseCategory, ScoreTrigger, Zone
from tests.conftest import World, auth, make_object
from tests.support_risk import NOW, add_ad, add_complaint, add_document, red_object


def _score(db: Session, obj: ConstructionObject, score: int, minutes: int) -> RiskScore:
    row = RiskScore(
        object_id=obj.id,
        score=score,
        zone=Zone.yellow,
        zone_reasons=["score_25_59"],
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
    add_complaint(db, obj, collective=True)  # not verified yet: a flag, no points
    headers = auth(world.users["mio_ust"])

    response = client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["score"], body["zone"], body["trigger"]) == (0, "green", "manual")
    assert body["zone_reasons"] == ["score_0_24"]
    assert set(body["breakdown"]) == {"factors", "needs_check", "legal_basis_status"}
    assert [item["code"] for item in body["breakdown"]["factors"]] == [
        "r1_no_legal_basis",
        "r2_money_offer",
        "r3_active_ads",
        "r4_collective_complaint",
        "r5_readiness_mismatch",
        "r6_stalled_or_delayed",
    ]
    assert [flag["code"] for flag in body["breakdown"]["needs_check"]] == [
        "legal_basis_unknown",
        "complaint_unverified",
    ]
    assert body["breakdown"]["legal_basis_status"] == "unknown"
    detail = client.get(f"/api/v1/objects/{obj.id}", headers=headers).json()
    assert detail["latest_score"]["calculated_at"] == body["calculated_at"]
    assert detail["latest_score"]["breakdown"] == body["breakdown"]
    assert (detail["score"], detail["zone"], detail["key_status"]) == (0, "green", "legal_basis_unknown")
    assert detail["next_check_at"] is not None


# ---------------------------------------------------------------- scenarios A, B, C of the case through the API


def _object_with_documents(
    client: TestClient, world: World, headers: dict[str, str], documents: list[tuple[str, str]]
) -> int:
    created = client.post(
        "/api/v1/objects", headers=headers, json={"name": "ЖК Сценарий", "territory_id": world.ust.id}
    )
    assert created.status_code == 201, created.text
    object_id: int = created.json()["id"]
    for doc_type, check_status in documents:
        response = client.post(
            f"/api/v1/objects/{object_id}/documents",
            headers=headers,
            data={"doc_type": doc_type, "check_status": check_status, "check_source": "housing_portal"},
        )
        assert response.status_code == 201, response.text
    return object_id


def _recalculate(client: TestClient, headers: dict[str, str], object_id: int) -> dict:
    response = client.post(f"/api/v1/objects/{object_id}/recalculate", headers=headers)
    assert response.status_code == 200, response.text
    body: dict = response.json()
    return body


def _drafts(client: TestClient, headers: dict[str, str], object_id: int) -> list[dict]:
    return list(client.get(f"/api/v1/signals?object_id={object_id}", headers=headers).json()["items"])


def test_scenario_a_through_the_api(client: TestClient, db: Session, world: World, sent_tasks: list) -> None:
    headers = auth(world.users["mio_ust"])
    object_id = _object_with_documents(client, world, headers, [])  # the basis was not checked
    add_ad(db, db.get_one(ConstructionObject, object_id), hits=((PhraseCategory.deposit, DetectedBy.dictionary, None),))
    sent_tasks.clear()

    body = _recalculate(client, headers, object_id)

    assert (body["score"], body["zone"]) == (35, "yellow")
    factors = {item["code"]: item for item in body["breakdown"]["factors"]}
    assert [factors[code]["triggered"] for code in ("r1_no_legal_basis", "r2_money_offer", "r3_active_ads")] == [
        False,
        True,
        True,
    ]
    assert [flag["code"] for flag in body["breakdown"]["needs_check"]] == ["legal_basis_unknown"]
    detail = client.get(f"/api/v1/objects/{object_id}", headers=headers).json()
    assert (detail["zone"], detail["key_status"]) == ("yellow", "money_offer")
    assert _drafts(client, headers, object_id) == [] and ("notify.red_zone", (object_id,)) not in sent_tasks
    dashboard_row = next(
        o for o in client.get("/api/v1/dashboard", headers=headers).json()["objects"] if o["id"] == object_id
    )
    assert (dashboard_row["score"], dashboard_row["zone"], dashboard_row["key_status"]) == (35, "yellow", "money_offer")


def test_scenario_b_through_the_api(client: TestClient, db: Session, world: World, sent_tasks: list) -> None:
    headers = auth(world.users["mio_ust"])
    object_id = _object_with_documents(
        client, world, headers, [("guarantee", "not_found"), ("dsu_permit", "not_found")]
    )
    add_ad(db, db.get_one(ConstructionObject, object_id), hits=((PhraseCategory.deposit, DetectedBy.dictionary, None),))
    sent_tasks.clear()

    body = _recalculate(client, headers, object_id)

    assert (body["score"], body["zone"], body["zone_reasons"]) == (70, "red", ["r1_and_r2"])
    assert body["breakdown"]["legal_basis_status"] == "absent_established"
    assert body["breakdown"]["needs_check"] == []
    r2 = next(item for item in body["breakdown"]["factors"] if item["code"] == "r2_money_offer")
    assert r2["evidence"][0]["fragment"] == "бронь" and r2["evidence"][0]["phrase_hit_id"]
    detail = client.get(f"/api/v1/objects/{object_id}", headers=headers).json()
    assert (detail["zone"], detail["key_status"]) == ("red", "no_legal_basis_with_offer")
    [draft] = _drafts(client, headers, object_id)
    assert (draft["status"], draft["zone"]) == ("requires_confirmation", "red")
    assert ("notify.red_zone", (object_id,)) in sent_tasks
    _recalculate(client, headers, object_id)
    assert len(_drafts(client, headers, object_id)) == 1  # the second calculation adds nothing


def test_scenario_c_through_the_api(client: TestClient, db: Session, world: World, sent_tasks: list) -> None:
    headers = auth(world.users["mio_ust"])
    object_id = _object_with_documents(client, world, headers, [("guarantee", "confirmed")])  # no MIO permit
    add_ad(db, db.get_one(ConstructionObject, object_id))  # plain advertising
    sent_tasks.clear()

    body = _recalculate(client, headers, object_id)

    assert (body["score"], body["zone"]) == (10, "green")
    assert body["breakdown"]["legal_basis_status"] == "confirmed"
    assert body["breakdown"]["needs_check"] == []
    factors = {item["code"]: item for item in body["breakdown"]["factors"]}
    assert not factors["r1_no_legal_basis"]["triggered"] and factors["r3_active_ads"]["triggered"]
    detail = client.get(f"/api/v1/objects/{object_id}", headers=headers).json()
    assert (detail["zone"], detail["key_status"]) == ("green", "active_ads")
    assert _drafts(client, headers, object_id) == [] and sent_tasks == []


def test_verifying_a_collective_complaint_changes_the_score_through_the_api(
    client: TestClient, db: Session, world: World
) -> None:
    headers = auth(world.users["mio_ust"])
    object_id = _object_with_documents(client, world, headers, [("guarantee", "confirmed")])
    created = client.post(
        f"/api/v1/objects/{object_id}/complaints",
        headers=headers,
        json={"received_at": "2026-10-10", "is_collective": True, "signatories_count": 12},
    )
    assert created.status_code == 201
    before = _recalculate(client, headers, object_id)
    assert before["score"] == 0 and [f["code"] for f in before["breakdown"]["needs_check"]] == ["complaint_unverified"]

    client.patch(f"/api/v1/complaints/{created.json()['id']}", headers=headers, json={"is_verified": True})

    after = _recalculate(client, headers, object_id)
    assert after["score"] == 15 and after["breakdown"]["needs_check"] == []


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
        ("r1_no_legal_basis", 35),
        ("r2_money_offer", 25),
        ("r3_active_ads", 10),
        ("r4_collective_complaint", 15),
        ("r5_readiness_mismatch", 10),
        ("r6_stalled_or_delayed", 5),
    ]
    assert body[0].keys() == {"code", "description", "weight", "is_active", "sort_order"}
    assert client.get("/api/v1/risk-factors", headers=auth(world.users["gask"])).status_code == 403


def test_weight_change_is_recorded_and_triggers_a_rescore_of_every_object(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    ust, semey = make_object(db, world.ust), make_object(db, world.semey, "ЖК Семей")
    add_document(db, ust, DocType.guarantee, CheckStatus.not_found)
    add_document(db, ust, DocType.dsu_permit, CheckStatus.not_found)  # the absence of a basis is established: R1
    admin = world.users["admin"]

    response = client.patch("/api/v1/risk-factors/r1_no_legal_basis", headers=auth(admin), json={"weight": 55})

    assert response.status_code == 200, response.text
    assert response.json()["weight"] == 55
    change = db.scalars(select(RiskFactorChange)).one()
    assert (change.code, change.old_weight, change.new_weight) == ("r1_no_legal_basis", 35, 55)
    assert (change.old_active, change.new_active, change.changed_by) == (True, True, admin.id)
    assert {args for name, args in sent_tasks if name == "risk.recalc_object"} >= {(ust.id,), (semey.id,)}
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "risk_factor.update")).one()
    assert entry.before["weight"] == 35 and entry.after["weight"] == 55

    client.post(f"/api/v1/objects/{ust.id}/recalculate", headers=auth(admin))
    assert db.get_one(ConstructionObject, ust.id).score == 55


def test_deactivating_a_factor_is_recorded(client: TestClient, db: Session, world: World) -> None:
    response = client.patch(
        "/api/v1/risk-factors/r3_active_ads", headers=auth(world.users["admin"]), json={"is_active": False}
    )
    assert response.json()["is_active"] is False
    change = db.scalars(select(RiskFactorChange)).one()
    assert (change.old_active, change.new_active, change.old_weight, change.new_weight) == (True, False, 10, 10)


def test_description_only_change_neither_logs_history_nor_rescores(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    make_object(db, world.ust)
    admin = auth(world.users["admin"])
    assert (
        client.patch(
            "/api/v1/risk-factors/r1_no_legal_basis", headers=admin, json={"description": "Новый текст"}
        ).status_code
        == 200
    )
    assert client.patch("/api/v1/risk-factors/r1_no_legal_basis", headers=admin, json={"weight": 35}).status_code == 200
    assert db.get_one(RiskFactor, "r1_no_legal_basis").description == "Новый текст"
    assert db.scalars(select(RiskFactorChange)).all() == []
    assert sent_tasks == []


def test_only_a_global_admin_may_change_weights(client: TestClient, db: Session, world: World) -> None:
    url = "/api/v1/risk-factors/r1_no_legal_basis"
    for role in ("mio_ust", "gask", "admin_semey"):
        assert client.patch(url, headers=auth(world.users[role]), json={"weight": 1}).status_code == 403
    assert client.patch(url, json={"weight": 1}).status_code == 401
    assert db.get_one(RiskFactor, "r1_no_legal_basis").weight == 35


@pytest.mark.parametrize(
    "body", [{"weight": 101}, {"weight": -101}, {"weight": None}, {"is_active": None}, {"description": " "}]
)
def test_invalid_factor_updates_are_rejected(client: TestClient, world: World, body: dict) -> None:
    response = client.patch("/api/v1/risk-factors/r1_no_legal_basis", headers=auth(world.users["admin"]), json=body)
    assert response.status_code == 422


def test_unknown_factor_is_not_found(client: TestClient, world: World) -> None:
    response = client.patch("/api/v1/risk-factors/nope", headers=auth(world.users["admin"]), json={"weight": 5})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "risk_factor_not_found"


def test_factor_history_lists_changes_newest_first_with_the_author(client: TestClient, world: World) -> None:
    admin = auth(world.users["admin"])
    client.patch("/api/v1/risk-factors/r1_no_legal_basis", headers=admin, json={"weight": 50})
    client.patch("/api/v1/risk-factors/r2_money_offer", headers=admin, json={"is_active": False})

    body = client.get("/api/v1/risk-factors/history", headers=auth(world.users["mio_ust"])).json()

    assert body["total"] == 2
    assert [item["code"] for item in body["items"]] == ["r2_money_offer", "r1_no_legal_basis"]
    assert body["items"][1]["old_weight"] == 35 and body["items"][1]["new_weight"] == 50
    assert body["items"][0]["changed_by_name"] == "t_admin"
    assert client.get("/api/v1/risk-factors/history", headers=auth(world.users["gask"])).status_code == 403


def test_lowered_weights_can_keep_an_object_out_of_red(client: TestClient, db: Session, world: World) -> None:
    obj = red_object(db, world.ust)  # R1 + R2 + R3 = 70
    admin = auth(world.users["admin"])
    assert client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=admin).json()["zone"] == "red"
    client.patch("/api/v1/risk-factors/r1_no_legal_basis", headers=admin, json={"weight": 10})

    body = client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=admin).json()

    assert (body["score"], body["zone"], body["zone_reasons"]) == (
        45,
        "yellow",
        ["score_25_59"],
    )  # still R1 and R2, below 60


def test_a_deactivated_r1_means_no_red_zone(client: TestClient, db: Session, world: World) -> None:
    obj = red_object(db, world.ust)
    admin = auth(world.users["admin"])
    client.patch("/api/v1/risk-factors/r1_no_legal_basis", headers=admin, json={"is_active": False})
    body = client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=admin).json()
    assert (body["score"], body["zone"]) == (35, "yellow")

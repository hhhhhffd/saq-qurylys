"""Verification of complaints (SPEC 3, 6.1 R4): the flag, who set it and when, CSV import and the rescoring event."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Complaint
from tests.conftest import World, auth, make_object

BASE = {"received_at": "2026-10-01", "is_collective": True, "signatories_count": 12}


def create(client: TestClient, world: World, object_id: int, who: str = "mio_ust", **extra: Any) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/objects/{object_id}/complaints", headers=auth(world.users[who]), json={**BASE, **extra}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def patch(client: TestClient, world: World, complaint_id: int, who: str = "mio_ust", **fields: Any) -> Any:
    return client.patch(f"/api/v1/complaints/{complaint_id}", headers=auth(world.users[who]), json=fields)


def test_a_new_complaint_is_not_verified(client: TestClient, db: Session, world: World) -> None:
    body = create(client, world, make_object(db, world.ust).id)
    assert (body["is_verified"], body["verified_by"], body["verified_at"]) == (False, None, None)


def test_creating_a_verified_complaint_records_who_and_when(client: TestClient, db: Session, world: World) -> None:
    body = create(client, world, make_object(db, world.ust).id, is_verified=True)
    assert body["is_verified"] is True
    assert body["verified_by"] == world.users["mio_ust"].id
    assert body["verified_at"] is not None


def test_verification_is_set_and_withdrawn_by_a_patch(client: TestClient, db: Session, world: World) -> None:
    complaint = create(client, world, make_object(db, world.ust).id)

    verified = patch(client, world, complaint["id"], is_verified=True)

    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert (body["is_verified"], body["verified_by"]) == (True, world.users["mio_ust"].id)
    assert body["verified_at"] is not None

    withdrawn = patch(client, world, complaint["id"], is_verified=False).json()
    assert (withdrawn["is_verified"], withdrawn["verified_by"], withdrawn["verified_at"]) == (False, None, None)


def test_saving_a_verified_complaint_again_keeps_the_original_verifier(
    client: TestClient, db: Session, world: World
) -> None:
    complaint = create(client, world, make_object(db, world.ust).id)
    first = patch(client, world, complaint["id"], is_verified=True).json()

    again = patch(client, world, complaint["id"], who="mio_region", is_verified=True, summary="Уточнено").json()
    other_field = patch(client, world, complaint["id"], who="mio_region", status="in_review").json()

    for body in (again, other_field):
        assert (body["verified_by"], body["verified_at"]) == (first["verified_by"], first["verified_at"])
    assert again["summary"] == "Уточнено"


def test_verification_is_audited_with_before_and_after(client: TestClient, db: Session, world: World) -> None:
    complaint = create(client, world, make_object(db, world.ust).id)
    patch(client, world, complaint["id"], is_verified=True)

    entries = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "complaint", AuditLog.entity_id == complaint["id"])
        .order_by(AuditLog.id)
    ).all()
    assert [entry.action for entry in entries] == ["complaint.create", "complaint.update"]
    update = entries[-1]
    assert (update.before["is_verified"], update.after["is_verified"]) == (False, True)
    assert update.before["verified_by"] is None and update.after["verified_by"] == world.users["mio_ust"].id
    assert update.after["verified_at"] is not None


def test_null_is_not_a_valid_verification_value(client: TestClient, db: Session, world: World) -> None:
    complaint = create(client, world, make_object(db, world.ust).id)
    assert patch(client, world, complaint["id"], is_verified=None).status_code == 422


def test_verification_triggers_a_rescore(client: TestClient, db: Session, world: World, sent_tasks: list) -> None:
    obj = make_object(db, world.ust)
    complaint = create(client, world, obj.id)
    sent_tasks.clear()
    patch(client, world, complaint["id"], is_verified=True)
    assert ("risk.recalc_object", (obj.id,)) in sent_tasks


def test_object_card_lists_the_verification_fields(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    create(client, world, obj.id, is_verified=True)
    [row] = client.get(f"/api/v1/objects/{obj.id}", headers=auth(world.users["mio_ust"])).json()["complaints"]
    assert row["is_verified"] is True and row["verified_by"] == world.users["mio_ust"].id
    assert row["verified_at"] is not None


def test_receiving_bodies_and_other_territories_cannot_verify(client: TestClient, db: Session, world: World) -> None:
    complaint = create(client, world, make_object(db, world.ust).id)
    assert patch(client, world, complaint["id"], who="gask", is_verified=True).status_code == 403
    assert patch(client, world, complaint["id"], who="mio_semey", is_verified=True).status_code == 404
    assert db.get_one(Complaint, complaint["id"]).is_verified is False


def _upload(client: TestClient, world: World, text: str, who: str = "mio_ust") -> dict[str, Any]:
    response = client.post(
        "/api/v1/complaints/import",
        headers=auth(world.users[who]),
        files={"file": ("complaints.csv", text.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_csv_import_sets_verification_and_leaves_it_alone_when_the_column_is_missing(
    client: TestClient, db: Session, world: World
) -> None:
    obj = make_object(db, world.ust)
    csv_text = (
        "object_code,received_at,source,external_id,is_collective,is_verified\n"
        f"{obj.code},2026-09-01,eotinish,EO-1,да,да\n"
        f"{obj.code},2026-09-02,eotinish,EO-2,да,нет\n"
        f"{obj.code},2026-09-03,eotinish,EO-3,да,\n"
        f"{obj.code},2026-09-04,eotinish,EO-4,да,возможно\n"
    )

    body = _upload(client, world, csv_text)

    assert (body["created"], [error["row"] for error in body["errors"]]) == (3, [5])
    rows = {c.external_id: c for c in db.scalars(select(Complaint).where(Complaint.object_id == obj.id))}
    assert rows["EO-1"].is_verified and rows["EO-1"].verified_by == world.users["mio_ust"].id
    assert rows["EO-1"].verified_at is not None
    assert not rows["EO-2"].is_verified and rows["EO-2"].verified_by is None
    assert not rows["EO-3"].is_verified

    # A later import without the column keeps the verification; with the column it can withdraw it.
    _upload(client, world, f"object_code,received_at,external_id,status\n{obj.code},2026-09-01,EO-1,in_review\n")
    db.refresh(rows["EO-1"])
    assert rows["EO-1"].is_verified is True
    _upload(client, world, f"object_code,received_at,external_id,is_verified\n{obj.code},2026-09-01,EO-1,нет\n")
    db.refresh(rows["EO-1"])
    assert (rows["EO-1"].is_verified, rows["EO-1"].verified_by, rows["EO-1"].verified_at) == (False, None, None)


def test_csv_import_verifies_an_existing_complaint_once(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    _upload(client, world, f"object_code,received_at,external_id\n{obj.code},2026-09-01,EO-9\n")
    _upload(
        client, world, f"object_code,received_at,external_id,is_verified\n{obj.code},2026-09-01,EO-9,да\n", "mio_ust"
    )
    complaint = db.scalars(select(Complaint).where(Complaint.external_id == "EO-9")).one()
    verified_at = complaint.verified_at
    assert complaint.is_verified and verified_at is not None
    _upload(
        client, world, f"object_code,received_at,external_id,is_verified\n{obj.code},2026-09-01,EO-9,да\n", "mio_region"
    )
    db.refresh(complaint)
    assert (complaint.verified_by, complaint.verified_at) == (world.users["mio_ust"].id, verified_at)

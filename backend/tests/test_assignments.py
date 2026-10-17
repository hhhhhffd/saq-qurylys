"""Assignments: creation rules, lists for the assignee and for control, completion permissions, overdue, audit."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, AuditLog, ConstructionObject, Notification
from app.models.enums import AssignmentStatus, NotificationKind
from app.modules.objects.service import territory_today
from tests.conftest import World, auth, make_object

API = "/api/v1"


def post(
    client: TestClient, db: Session, world: World, obj: ConstructionObject, author: str, assignee: str, days: int = 3
) -> Any:
    due = territory_today(db, obj.territory_id) + timedelta(days=days)
    return client.post(
        f"{API}/objects/{obj.id}/assignments",
        headers=auth(world.users[author]),
        json={"assignee_id": world.users[assignee].id, "task": "Проверить сведения", "due_date": due.isoformat()},
    )


def test_create_lists_and_notification(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    response = post(client, db, world, obj, "mio_ust", "mio_region")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "open"
    assert body["is_overdue"] is False and body["days_overdue"] == 0
    assert body["object"]["id"] == obj.id
    assert body["assignee_name"] == "t_mio_region" and body["author_name"] == "t_mio_ust"

    object_list = client.get(f"{API}/objects/{obj.id}/assignments", headers=auth(world.users["mio_ust"]))
    assert [row["id"] for row in object_list.json()] == [body["id"]]

    note = db.scalars(select(Notification).where(Notification.entity_id == body["id"])).one()
    assert note.kind is NotificationKind.assignment_new
    assert note.user_id == world.users["mio_region"].id

    entry = db.scalars(select(AuditLog).where(AuditLog.action == "assignment.create")).one()
    assert entry.entity_id == body["id"] and entry.after["task"] == "Проверить сведения"


def test_create_permissions_and_validation(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    for role in ("gask", "law"):
        assert post(client, db, world, obj, role, "mio_ust").status_code == 403
    # An object of another city is hidden from the officer of Semey.
    assert post(client, db, world, obj, "mio_semey", "mio_semey").status_code == 404
    # The assignee must cover the object territory, be staff and be active.
    assert post(client, db, world, obj, "mio_ust", "mio_semey").status_code == 422
    assert post(client, db, world, obj, "mio_ust", "gask").status_code == 422
    # Past dates are refused.
    assert post(client, db, world, obj, "mio_ust", "mio_ust", days=-1).status_code == 422
    assert post(client, db, world, obj, "mio_ust", "mio_ust", days=0).status_code == 201
    blank = client.post(
        f"{API}/objects/{obj.id}/assignments",
        headers=auth(world.users["mio_ust"]),
        json={"assignee_id": world.users["mio_ust"].id, "task": "   ", "due_date": "2999-01-01"},
    )
    assert blank.status_code == 422


def test_assignees_list(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    response = client.get(
        f"{API}/assignments/assignees", params={"object_id": obj.id}, headers=auth(world.users["mio_ust"])
    )
    assert response.status_code == 200
    names = {row["full_name"] for row in response.json()}
    assert {"t_admin", "t_mio_ust", "t_mio_region"} <= names
    assert not names & {"t_mio_semey", "t_admin_semey", "t_gask", "t_law"}
    hidden = client.get(
        f"{API}/assignments/assignees", params={"object_id": obj.id}, headers=auth(world.users["mio_semey"])
    )
    assert hidden.status_code == 404


def test_mine_and_control_filters_and_overdue(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    today = territory_today(db, obj.territory_id)
    late = Assignment(
        object_id=obj.id,
        author_id=world.users["mio_ust"].id,
        assignee_id=world.users["mio_region"].id,
        task="Просроченное",
        due_date=today - timedelta(days=4),
    )
    db.add(late)
    db.flush()
    fresh_id = post(client, db, world, obj, "mio_ust", "mio_region", days=2).json()["id"]
    other_id = post(client, db, world, obj, "mio_ust", "mio_ust", days=1).json()["id"]
    semey_obj = make_object(db, world.semey)
    semey_id = post(client, db, world, semey_obj, "admin", "mio_semey", days=1).json()["id"]

    headers = auth(world.users["mio_region"])
    mine = client.get(f"{API}/assignments", params={"mine": True}, headers=headers).json()
    # Overdue first, then by date.
    assert [row["id"] for row in mine["items"]] == [late.id, fresh_id]
    assert mine["total"] == 2
    assert mine["items"][0]["is_overdue"] is True and mine["items"][0]["days_overdue"] == 4

    control = client.get(f"{API}/assignments", headers=auth(world.users["mio_ust"])).json()
    assert {row["id"] for row in control["items"]} == {late.id, fresh_id, other_id}
    assert semey_id not in {row["id"] for row in control["items"]}
    overdue = client.get(f"{API}/assignments", params={"overdue": True}, headers=auth(world.users["admin"])).json()
    assert [row["id"] for row in overdue["items"]] == [late.id]
    not_overdue = client.get(f"{API}/assignments", params={"overdue": False}, headers=auth(world.users["admin"])).json()
    assert late.id not in {row["id"] for row in not_overdue["items"]}
    assert client.get(f"{API}/assignments", headers=auth(world.users["gask"])).status_code == 403

    done = client.patch(f"{API}/assignments/{late.id}", headers=headers, json={"status": "done", "result": "Проверено"})
    assert done.status_code == 200
    assert done.json()["is_overdue"] is False and done.json()["completed_at"] is not None
    by_status = client.get(f"{API}/assignments", params={"status": "done"}, headers=headers).json()
    assert [row["id"] for row in by_status["items"]] == [late.id]


def test_complete_permissions_and_audit(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    assignment_id = post(client, db, world, obj, "mio_ust", "mio_region").json()["id"]
    url = f"{API}/assignments/{assignment_id}"
    body = {"status": "done", "result": "Всё в порядке"}

    assert client.patch(url, headers=auth(world.users["mio_semey"]), json=body).status_code == 404
    assert client.patch(url, headers=auth(world.users["gask"]), json=body).status_code == 403
    # An administrator of another city does not see the assignment at all.
    other = client.patch(url, headers=auth(world.users["admin_semey"]), json=body)
    assert other.status_code == 404
    assert client.patch(url, headers=auth(world.users["mio_region"]), json={"status": "done"}).status_code == 422
    assert client.patch(url, headers=auth(world.users["mio_region"]), json={"status": "cancelled"}).status_code == 403

    response = client.patch(url, headers=auth(world.users["mio_region"]), json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "done" and response.json()["result"] == "Всё в порядке"
    assert client.patch(url, headers=auth(world.users["mio_ust"]), json=body).status_code == 409

    entry = db.scalars(select(AuditLog).where(AuditLog.action == "assignment.update")).one()
    assert entry.before["status"] == "open" and entry.after["status"] == "done"


def test_other_officer_cannot_complete(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    assignment_id = post(client, db, world, obj, "mio_ust", "admin").json()["id"]
    response = client.patch(
        f"{API}/assignments/{assignment_id}",
        headers=auth(world.users["mio_region"]),
        json={"status": "done", "result": "Сделано"},
    )
    assert response.status_code == 403


def test_cancel_and_reassign(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    assignment_id = post(client, db, world, obj, "mio_ust", "mio_region").json()["id"]
    url = f"{API}/assignments/{assignment_id}"
    new_due = (territory_today(db, obj.territory_id) + timedelta(days=10)).isoformat()

    assert client.patch(url, headers=auth(world.users["mio_region"]), json={"due_date": new_due}).status_code == 403
    moved = client.patch(
        url,
        headers=auth(world.users["mio_ust"]),
        json={"due_date": new_due, "assignee_id": world.users["admin"].id},
    )
    assert moved.status_code == 200
    assert moved.json()["due_date"] == new_due and moved.json()["assignee_name"] == "t_admin"
    assert db.scalars(select(Notification).where(Notification.user_id == world.users["admin"].id)).one()
    bad = client.patch(url, headers=auth(world.users["mio_ust"]), json={"assignee_id": world.users["gask"].id})
    assert bad.status_code == 422

    cancelled = client.patch(url, headers=auth(world.users["admin"]), json={"status": "cancelled"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == AssignmentStatus.cancelled.value

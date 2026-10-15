import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import World, auth, make_object


@pytest.mark.parametrize("role", ["gask", "law"])
def test_receiving_bodies_cannot_read_or_write_registry(
    client: TestClient, db: Session, world: World, role: str
) -> None:
    obj = make_object(db, world.ust)
    headers = auth(world.users[role])
    assert client.get("/api/v1/objects", headers=headers).status_code == 403
    assert client.get(f"/api/v1/objects/{obj.id}", headers=headers).status_code == 403
    assert (
        client.post("/api/v1/objects", headers=headers, json={"name": "X", "territory_id": world.ust.id}).status_code
        == 403
    )
    assert client.get("/api/v1/developers", headers=headers).status_code == 403
    assert client.get("/api/v1/settings", headers=headers).status_code == 403
    assert client.get("/api/v1/audit", headers=headers).status_code == 403


def test_admin_only_endpoints_reject_mio_officer(client: TestClient, world: World) -> None:
    headers = auth(world.users["mio_region"])
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    assert client.put("/api/v1/settings", headers=headers, json={"review_days": 3}).status_code == 403
    assert (
        client.post(
            "/api/v1/holidays", headers=headers, json={"day": "2026-01-01", "kind": "holiday", "name": "x"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/settings", headers=headers).status_code == 200  # reading is allowed


def test_unauthenticated_requests_are_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/objects").status_code == 401
    assert client.get("/api/v1/health").status_code == 200


def test_object_list_and_detail_are_territory_scoped(client: TestClient, db: Session, world: World) -> None:
    ust_object = make_object(db, world.ust, "ЖК Усть")
    semey_object = make_object(db, world.semey, "ЖК Семей")

    ust_view = client.get("/api/v1/objects", headers=auth(world.users["mio_ust"])).json()
    assert [item["id"] for item in ust_view["items"]] == [ust_object.id]
    assert ust_view["total"] == 1

    region_ids = {
        item["id"] for item in client.get("/api/v1/objects", headers=auth(world.users["mio_region"])).json()["items"]
    }
    assert region_ids == {ust_object.id, semey_object.id}
    admin_ids = {
        item["id"] for item in client.get("/api/v1/objects", headers=auth(world.users["admin"])).json()["items"]
    }
    assert {ust_object.id, semey_object.id} <= admin_ids

    # Out-of-scope objects look missing, not forbidden.
    hidden = client.get(f"/api/v1/objects/{semey_object.id}", headers=auth(world.users["mio_ust"]))
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "object_not_found"
    assert (
        client.patch(
            f"/api/v1/objects/{semey_object.id}", headers=auth(world.users["mio_ust"]), json={"name": "x"}
        ).status_code
        == 404
    )


def test_cannot_create_object_outside_territory(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/objects",
        headers=auth(world.users["mio_ust"]),
        json={"name": "ЖК Чужой", "territory_id": world.semey.id},
    )
    assert response.status_code == 403


def test_scope_applies_to_nested_resources(client: TestClient, db: Session, world: World) -> None:
    semey_object = make_object(db, world.semey)
    headers = auth(world.users["mio_ust"])
    assert (
        client.post(
            f"/api/v1/objects/{semey_object.id}/complaints", headers=headers, json={"received_at": "2026-01-01"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/objects/{semey_object.id}/linked-entities",
            headers=headers,
            json={"kind": "website", "value": "x.kz"},
        ).status_code
        == 404
    )


def test_territory_tree_is_scoped(client: TestClient, world: World) -> None:
    city_user_tree = client.get("/api/v1/territories", headers=auth(world.users["mio_ust"])).json()
    assert [node["code"] for node in city_user_tree] == ["ust-kamenogorsk"]
    region_tree = client.get("/api/v1/territories", headers=auth(world.users["mio_region"])).json()
    assert [node["code"] for node in region_tree] == ["vko"]
    assert {child["code"] for child in region_tree[0]["children"]} == {"ust-kamenogorsk", "semey"}


def test_user_management_respects_admin_scope(client: TestClient, world: World) -> None:
    users = client.get("/api/v1/users", headers=auth(world.users["admin"])).json()
    assert users["total"] >= 6
    created = client.post(
        "/api/v1/users",
        headers=auth(world.users["admin"]),
        json={
            "username": "New.User",
            "full_name": "Новый",
            "password": "long-enough-pw",
            "role": "mio_officer",
            "territory_id": world.ust.id,
        },
    )
    assert created.status_code == 201
    assert created.json()["username"] == "new.user"
    assert "password" not in created.json()
    duplicate = client.post(
        "/api/v1/users",
        headers=auth(world.users["admin"]),
        json={"username": "new.user", "full_name": "Дубль", "password": "long-enough-pw", "role": "gask"},
    )
    assert duplicate.status_code == 409
    me = world.users["admin"]
    self_demote = client.patch(f"/api/v1/users/{me.id}", headers=auth(me), json={"is_active": False})
    assert self_demote.status_code == 409

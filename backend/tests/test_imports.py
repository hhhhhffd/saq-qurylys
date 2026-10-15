from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AppUser, AuditLog, Complaint, ConstructionObject, Developer
from tests.conftest import World, auth, make_object


def _upload(client: TestClient, url: str, content: str | bytes, user: AppUser, encoding: str = "utf-8") -> Response:
    raw = content.encode(encoding) if isinstance(content, str) else content
    response: Response = client.post(url, headers=auth(user), files={"file": ("import.csv", raw, "text/csv")})
    return response


OBJECTS_CSV = """name,territory_code,district,developer_bin,developer_name,aliases,address,lat,lon,planned_completion,construction_status
ЖК Первый,ust-kamenogorsk,Центральный,111111111111,ТОО Первый,Первый квартал|Pervyi,ул. Мира 1,49.95,82.61,2027-12-31,active
,ust-kamenogorsk,,,,,,,,,
ЖК Без города,nowhere,,,,,,,,,
ЖК Плохая дата,ust-kamenogorsk,,,,,,,,31.31.2027,
ЖК Плохой статус,ust-kamenogorsk,,,,,,,,,frozen
ЖК Чужой,semey,,,,,,,,,
ЖК Координаты,ust-kamenogorsk,,,,,,49.95,,,
ЖК Второй,ust-kamenogorsk,Нет такого района,,,,,,,,
ЖК Третий,ust-kamenogorsk,,222222222222,,,,,,,
ЖК Четвёртый,ust-kamenogorsk,,,,,,"49,96","82,62",01.06.2028,stalled
"""


def test_objects_csv_reports_errors_per_row(client: TestClient, db: Session, world: World) -> None:
    response = _upload(client, "/api/v1/objects/import", OBJECTS_CSV, world.users["mio_ust"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2  # "ЖК Первый" and "ЖК Четвёртый"
    assert body["updated"] == 0
    errors = {item["row"]: item["message"] for item in body["errors"]}
    assert set(errors) == {3, 4, 5, 6, 7, 8, 9, 10}
    assert "name" in errors[3]
    assert "nowhere" in errors[4]
    assert "дата" in errors[5]
    assert "frozen" in errors[6]
    assert "semey" in errors[7]  # outside the user's territory
    assert "lat" in errors[8]
    assert "район" in errors[9].lower()
    assert "222222222222" in errors[10]  # unknown developer without a name

    first = db.scalars(select(ConstructionObject).where(ConstructionObject.name == "ЖК Первый")).one()
    assert first.aliases == ["Первый квартал", "Pervyi"]
    assert first.district_id == world.district.id and first.lat == 49.95
    developer = db.scalars(select(Developer).where(Developer.bin == "111111111111")).one()
    assert first.developer_id == developer.id
    fourth = db.scalars(select(ConstructionObject).where(ConstructionObject.name == "ЖК Четвёртый")).one()
    assert (fourth.lat, fourth.lon) == (49.96, 82.62) and fourth.stalled_since is not None
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "object.import_create")) == 2


def test_objects_csv_reimport_updates_instead_of_duplicating(client: TestClient, db: Session, world: World) -> None:
    csv_text = "name;territory_code;address;cadastral_number\nЖК Повтор;ust-kamenogorsk;ул. А;05-123\n"
    first = _upload(client, "/api/v1/objects/import", csv_text, world.users["mio_ust"], encoding="cp1251").json()
    assert first == {"created": 1, "updated": 0, "errors": []}
    second = _upload(client, "/api/v1/objects/import", csv_text, world.users["mio_ust"]).json()
    assert second["created"] == 0 and second["updated"] == 1
    assert (
        db.scalar(select(func.count()).select_from(ConstructionObject).where(ConstructionObject.name == "ЖК Повтор"))
        == 1
    )

    code = db.scalars(select(ConstructionObject.code).where(ConstructionObject.name == "ЖК Повтор")).one()
    by_code = _upload(
        client,
        "/api/v1/objects/import",
        f"code,name,territory_code,land_purpose\n{code},ЖК Повтор,ust-kamenogorsk,жилая застройка\n",
        world.users["mio_ust"],
    ).json()
    assert by_code["updated"] == 1
    missing = _upload(
        client,
        "/api/v1/objects/import",
        "code,name,territory_code\nSQ-OBJ-99999999,X,ust-kamenogorsk\n",
        world.users["mio_ust"],
    ).json()
    assert missing["errors"][0]["row"] == 2 and "SQ-OBJ-99999999" in missing["errors"][0]["message"]


def test_objects_csv_file_level_errors(client: TestClient, world: World) -> None:
    missing_columns = _upload(client, "/api/v1/objects/import", "name\nЖК\n", world.users["mio_ust"])
    assert missing_columns.status_code == 422
    assert missing_columns.json()["detail"]["code"] == "csv_missing_columns"
    assert "territory_code" in missing_columns.json()["detail"]["message"]
    assert _upload(client, "/api/v1/objects/import", "", world.users["mio_ust"]).status_code == 422
    assert _upload(client, "/api/v1/objects/import", "name,territory_code\n", world.users["gask"]).status_code == 403


def test_complaints_csv_import(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    semey_obj = make_object(db, world.semey)
    csv_text = (
        "object_code,received_at,source,external_id,is_collective,signatories_count,summary,status,confirmed_payments\n"
        f"{obj.code},2026-09-01,eotinish,EO-1,да,12,Коллективная жалоба,new,нет\n"
        f"{obj.code},05.09.2026,eotinish,EO-2,0,1,Заявитель внёс бронь,in_review,1\n"
        f"SQ-OBJ-0,2026-09-01,eotinish,EO-3,,,,,\n"
        f"{obj.code},вчера,eotinish,EO-4,,,,,\n"
        f"{obj.code},2026-09-01,eotinish,EO-5,возможно,,,,\n"
        f"{obj.code},2026-09-01,eotinish,EO-6,,0,,,\n"
        f"{semey_obj.code},2026-09-01,eotinish,EO-7,,,,,\n"
    )
    body = _upload(client, "/api/v1/complaints/import", csv_text, world.users["mio_ust"]).json()
    assert body["created"] == 2 and body["updated"] == 0
    assert [e["row"] for e in body["errors"]] == [4, 5, 6, 7, 8]

    first = db.scalars(select(Complaint).where(Complaint.external_id == "EO-1")).one()
    assert first.is_collective and first.signatories_count == 12 and not first.confirmed_payments
    second = db.scalars(select(Complaint).where(Complaint.external_id == "EO-2")).one()
    assert second.confirmed_payments and second.status.value == "in_review"

    again = _upload(
        client,
        "/api/v1/complaints/import",
        f"object_code,received_at,external_id,status\n{obj.code},2026-09-01,EO-1,closed\n",
        world.users["mio_ust"],
    ).json()
    assert again["created"] == 0 and again["updated"] == 1
    db.refresh(first)
    assert first.status.value == "closed" and first.is_collective  # untouched columns keep their values


def test_manual_complaint_crud_and_duplicate_external_id(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    headers = auth(world.users["mio_ust"])
    payload = {"received_at": "2026-09-10", "source": "eotinish", "external_id": "EO-100", "summary": "Не сдан дом"}
    created = client.post(f"/api/v1/objects/{obj.id}/complaints", headers=headers, json=payload)
    assert created.status_code == 201
    assert client.post(f"/api/v1/objects/{obj.id}/complaints", headers=headers, json=payload).status_code == 409
    patched = client.patch(
        f"/api/v1/complaints/{created.json()['id']}",
        headers=headers,
        json={"confirmed_payments": True, "status": "in_review"},
    )
    assert patched.status_code == 200 and patched.json()["confirmed_payments"] is True
    assert (
        client.patch(f"/api/v1/complaints/{created.json()['id']}", headers=headers, json={"status": None}).status_code
        == 422
    )
    detail = client.get(f"/api/v1/objects/{obj.id}", headers=headers).json()
    assert len(detail["complaints"]) == 1

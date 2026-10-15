"""Signal card API: lifecycle, role and territory rules, audit trail and notifications."""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar import add_working_days
from app.models import AuditLog, ConstructionObject, Notification, SignalCard, Territory
from app.models.enums import NotificationKind, SignalStatus, Zone
from app.modules.settings.service import save_settings
from app.modules.signals import pdf, router
from app.modules.signals.service import local_today
from tests.conftest import World, auth, make_object
from tests.support_risk import add_complaint, red_object

API = "/api/v1/signals"
NUMBER = re.compile(r"^SQ-\d{4}-\d{4,}$")


def create(client: TestClient, world: World, obj: ConstructionObject, who: str = "mio_ust") -> dict[str, Any]:
    response = client.post(API, headers=auth(world.users[who]), json={"object_id": obj.id})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def post(client: TestClient, world: World, who: str, path: str, body: dict[str, Any] | None = None) -> Any:
    return client.post(f"{API}{path}", headers=auth(world.users[who]), json=body)


def send(client: TestClient, world: World, signal_id: int, recipient: str = "gask", who: str = "mio_ust") -> Any:
    return post(client, world, who, f"/{signal_id}/confirm-and-send", {"recipient": recipient})


def kinds_for(db: Session, user_id: int) -> list[NotificationKind]:
    rows = db.scalars(select(Notification).where(Notification.user_id == user_id).order_by(Notification.id))
    return [row.kind for row in rows]


def audit_actions(db: Session, signal_id: int) -> list[str]:
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "signal_card", AuditLog.entity_id == signal_id)
        .order_by(AuditLog.id)
    )
    return [row.action for row in rows]


def _local_today(db: Session, obj: ConstructionObject) -> date:
    return local_today(db.get_one(Territory, obj.territory_id).timezone)


# ---------------------------------------------------------------- creation


def test_officer_creates_a_manual_card(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_complaint(db, obj, collective=True)
    client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=auth(world.users["mio_ust"]))

    card = create(client, world, obj)

    assert NUMBER.match(card["number"])
    assert (card["status"], card["origin"], card["recipient"], card["due_date"]) == (
        "requires_confirmation",
        "manual",
        None,
        None,
    )
    assert (card["object_id"], card["object_name"], card["zone"], card["is_overdue"]) == (
        obj.id,
        obj.name,
        "yellow",
        False,
    )
    assert card["review_days"] == 5
    assert card["created_by"] == world.users["mio_ust"].id
    assert card["sections"]["object_developer"]["object_code"] == obj.code
    assert [item["code"] for item in card["sections"]["risk_factors"]] == ["no_permit", "complaints"]
    assert [(entry["action"], entry["username"]) for entry in card["audit"]] == [("signal_card.create", "t_mio_ust")]


@pytest.mark.parametrize("who", ["admin", "gask", "law"])
def test_only_officers_create_cards(client: TestClient, db: Session, world: World, who: str) -> None:
    obj = make_object(db, world.ust)
    assert post(client, world, who, "", {"object_id": obj.id}).status_code == 403


def test_card_is_created_only_inside_the_officers_territory(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    assert post(client, world, "mio_semey", "", {"object_id": obj.id}).status_code == 404
    assert post(client, world, "mio_ust", "", {"object_id": 999_999}).status_code == 404
    assert post(client, world, "mio_ust", "", {}).status_code == 422


# ---------------------------------------------------------------- editing


def test_officer_edits_the_editable_parts(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    patch: dict[str, Any] = {
        "recipient": "law_enforcement",
        "review_days": 3,
        "sections": {
            "note": "Проверить в первую очередь",
            "proposed_measures": ["site_inspection", "request_documents", "site_inspection"],
            "scheme_payments": {
                "payment_schemes": ["deposit"],
                "contract_types": ["Предварительный договор"],
                "confirmed_payments_note": "Два заявителя",
            },
            "object_developer": {"object_name": "Подмена"},  # snapshot sections are not editable
        },
    }

    response = client.patch(f"{API}/{card['id']}", headers=auth(world.users["mio_ust"]), json=patch)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["recipient"], body["review_days"], body["status"]) == ("law_enforcement", 3, "requires_confirmation")
    sections = body["sections"]
    assert sections["note"] == "Проверить в первую очередь"
    assert sections["proposed_measures"] == ["site_inspection", "request_documents"]
    assert sections["scheme_payments"]["payment_schemes"] == ["deposit"]
    assert sections["route"] == {"recipient": "law_enforcement", "review_days": 3}
    assert sections["object_developer"]["object_name"] == card["sections"]["object_developer"]["object_name"]
    update = body["audit"][-1]
    assert update["action"] == "signal_card.update"
    assert update["before"]["review_days"] == 5 and update["after"]["review_days"] == 3
    assert (
        update["before"]["sections"]["note"] == "" and update["after"]["sections"]["note"] == patch["sections"]["note"]
    )


def test_the_frontend_may_send_the_whole_sections_object_back(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    sections = {**card["sections"], "note": "Через форму"}
    response = client.patch(
        f"{API}/{card['id']}",
        headers=auth(world.users["mio_ust"]),
        json={"sections": sections, "recipient": "gask", "review_days": 5},
    )
    assert response.status_code == 200, response.text
    assert response.json()["sections"]["note"] == "Через форму"
    assert response.json()["sections"]["route"]["recipient"] == "gask"


def test_a_patch_without_changes_leaves_no_trace(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    response = client.patch(f"{API}/{card['id']}", headers=auth(world.users["mio_ust"]), json={"review_days": 5})
    assert response.status_code == 200
    assert audit_actions(db, card["id"]) == ["signal_card.create"]


@pytest.mark.parametrize(
    "patch",
    [
        {"review_days": 0},
        {"review_days": 61},
        {"recipient": "everyone"},
        {"sections": {"proposed_measures": ["bribe"]}},
        {
            "sections": {
                "scheme_payments": {"payment_schemes": ["barter"], "contract_types": [], "confirmed_payments_note": ""}
            }
        },
    ],
)
def test_invalid_edits_are_rejected(client: TestClient, db: Session, world: World, patch: dict[str, Any]) -> None:
    card = create(client, world, make_object(db, world.ust))
    assert client.patch(f"{API}/{card['id']}", headers=auth(world.users["mio_ust"]), json=patch).status_code == 422


@pytest.mark.parametrize("who", ["admin", "gask", "law", "mio_semey"])
def test_only_the_territory_officer_edits(client: TestClient, db: Session, world: World, who: str) -> None:
    card = create(client, world, make_object(db, world.ust))
    response = client.patch(f"{API}/{card['id']}", headers=auth(world.users[who]), json={"review_days": 2})
    assert response.status_code in (403, 404)
    assert db.get_one(SignalCard, card["id"]).review_days == 5


# ---------------------------------------------------------------- lifecycle


def test_full_lifecycle(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    card = create(client, world, obj)
    signal_id = card["id"]
    mio, gask = world.users["mio_ust"], world.users["gask"]

    sent = send(client, world, signal_id)
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert (body["status"], body["recipient"], body["sent_by"]) == ("sent", "gask", mio.id)
    assert body["sent_at"] is not None
    assert abs(datetime.fromisoformat(body["sent_at"]) - datetime.now(UTC)) < timedelta(minutes=1)
    assert body["due_date"] == add_working_days(db, _local_today(db, obj), 5).isoformat()
    assert body["is_overdue"] is False
    assert body["sections"]["route"] == {"recipient": "gask", "review_days": 5}
    assert kinds_for(db, gask.id) == [NotificationKind.signal_sent]
    assert kinds_for(db, mio.id) == []  # the sender is not told about their own action
    notification = db.scalars(select(Notification).where(Notification.user_id == gask.id)).one()
    assert (notification.entity_type, notification.entity_id) == ("signal_card", signal_id)
    assert notification.payload["number"] == card["number"]

    answered = post(
        client, world, "gask", f"/{signal_id}/response", {"response_text": "Проверка проведена, нарушений нет"}
    )
    assert answered.status_code == 200, answered.text
    assert (answered.json()["status"], answered.json()["responded_by"]) == ("responded", gask.id)
    assert answered.json()["response_text"] == "Проверка проведена, нарушений нет"
    assert answered.json()["response_at"] is not None
    assert NotificationKind.signal_responded in kinds_for(db, mio.id)
    assert NotificationKind.signal_responded in kinds_for(db, world.users["mio_region"].id)
    assert NotificationKind.signal_responded not in kinds_for(db, gask.id)

    closed = post(client, world, "mio_ust", f"/{signal_id}/close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert audit_actions(db, signal_id) == [
        "signal_card.create",
        "signal_card.confirm_and_send",
        "signal_card.respond",
        "signal_card.close",
    ]


def test_confirm_and_send_can_choose_the_recipient(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    client.patch(f"{API}/{card['id']}", headers=auth(world.users["mio_ust"]), json={"recipient": "gask"})
    response = send(client, world, card["id"], "law_enforcement")
    assert response.json()["recipient"] == "law_enforcement"
    assert kinds_for(db, world.users["law"].id) == [NotificationKind.signal_sent]
    assert kinds_for(db, world.users["gask"].id) == []


def test_confirm_and_send_requires_a_recipient(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    assert post(client, world, "mio_ust", f"/{card['id']}/confirm-and-send", {}).status_code == 422
    assert send(client, world, card["id"], "police").status_code == 422
    assert db.get_one(SignalCard, card["id"]).status is SignalStatus.requires_confirmation


@pytest.mark.parametrize("who", ["gask", "law", "admin", "mio_semey"])
def test_nobody_but_the_territory_officer_can_send(client: TestClient, db: Session, world: World, who: str) -> None:
    card = create(client, world, make_object(db, world.ust))
    response = send(client, world, card["id"], who=who)
    assert response.status_code in (403, 404)
    unchanged = db.get_one(SignalCard, card["id"])
    assert (unchanged.status, unchanged.sent_at, unchanged.sent_by) == (SignalStatus.requires_confirmation, None, None)


def test_the_regional_officer_may_send_cards_of_a_city_below(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    assert send(client, world, card["id"], who="mio_region").status_code == 200


def test_a_card_cannot_be_sent_twice(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    assert send(client, world, card["id"]).status_code == 200
    again = send(client, world, card["id"])
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "signal_invalid_status"
    assert kinds_for(db, world.users["gask"].id) == [NotificationKind.signal_sent]


def test_return_and_rework(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust), who="mio_ust")
    signal_id = card["id"]

    returned = post(client, world, "mio_region", f"/{signal_id}/return", {"comment": "Добавьте сведения о платежах"})

    assert returned.status_code == 200, returned.text
    assert (returned.json()["status"], returned.json()["return_comment"]) == (
        "returned",
        "Добавьте сведения о платежах",
    )
    assert kinds_for(db, world.users["mio_ust"].id) == [NotificationKind.signal_returned]  # the author is told
    assert kinds_for(db, world.users["mio_region"].id) == []

    assert send(client, world, signal_id).status_code == 409  # must be reworked first
    edited = client.patch(
        f"{API}/{signal_id}", headers=auth(world.users["mio_ust"]), json={"sections": {"note": "Дополнено"}}
    )
    assert edited.json()["status"] == "requires_confirmation"
    assert send(client, world, signal_id).status_code == 200
    assert audit_actions(db, signal_id) == [
        "signal_card.create",
        "signal_card.return",
        "signal_card.update",
        "signal_card.confirm_and_send",
    ]


def test_returned_card_unchanged_by_an_empty_edit_stays_returned(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    post(client, world, "mio_ust", f"/{card['id']}/return", {"comment": "Доработать"})
    response = client.patch(f"{API}/{card['id']}", headers=auth(world.users["mio_ust"]), json={"review_days": 5})
    assert response.json()["status"] == "returned"


def test_returning_an_automatic_draft_tells_every_officer_but_the_actor(
    client: TestClient, db: Session, world: World
) -> None:
    obj = red_object(db, world.ust)
    client.post(f"/api/v1/objects/{obj.id}/recalculate", headers=auth(world.users["mio_ust"]))
    draft = db.scalars(select(SignalCard).where(SignalCard.object_id == obj.id)).one()
    assert draft.created_by is None

    response = post(client, world, "mio_ust", f"/{draft.id}/return", {"comment": "Нужны уточнения"})

    assert response.status_code == 200
    assert kinds_for(db, world.users["mio_region"].id) == [NotificationKind.signal_returned]
    assert kinds_for(db, world.users["mio_ust"].id) == []


@pytest.mark.parametrize("body", [None, {}, {"comment": ""}, {"comment": "   "}])
def test_return_requires_a_comment(client: TestClient, db: Session, world: World, body: dict[str, Any] | None) -> None:
    card = create(client, world, make_object(db, world.ust))
    assert post(client, world, "mio_ust", f"/{card['id']}/return", body).status_code == 422
    assert db.get_one(SignalCard, card["id"]).status is SignalStatus.requires_confirmation


@pytest.mark.parametrize("who", ["gask", "law", "admin"])
def test_only_officers_return_and_close(client: TestClient, db: Session, world: World, who: str) -> None:
    card = create(client, world, make_object(db, world.ust))
    assert post(client, world, who, f"/{card['id']}/return", {"comment": "x"}).status_code == 403
    assert post(client, world, who, f"/{card['id']}/close").status_code == 403


def test_response_is_for_the_addressed_body_only(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    signal_id = card["id"]
    answer = {"response_text": "Результат"}

    # Nobody can answer a draft; receiving bodies do not even see it.
    assert post(client, world, "gask", f"/{signal_id}/response", answer).status_code == 404
    send(client, world, signal_id, "gask")

    assert post(client, world, "mio_ust", f"/{signal_id}/response", answer).status_code == 403  # the MIO cannot respond
    assert post(client, world, "admin", f"/{signal_id}/response", answer).status_code == 403
    assert post(client, world, "law", f"/{signal_id}/response", answer).status_code == 404  # addressed to another body
    assert db.get_one(SignalCard, signal_id).status is SignalStatus.sent

    assert post(client, world, "gask", f"/{signal_id}/response", {"response_text": " "}).status_code == 422
    assert post(client, world, "gask", f"/{signal_id}/response", answer).status_code == 200
    again = post(client, world, "gask", f"/{signal_id}/response", answer)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "signal_invalid_status"


def test_close_only_after_a_response(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    assert post(client, world, "mio_ust", f"/{card['id']}/close").status_code == 409
    send(client, world, card["id"])
    assert post(client, world, "mio_ust", f"/{card['id']}/close").status_code == 409
    post(client, world, "gask", f"/{card['id']}/response", {"response_text": "ok"})
    assert post(client, world, "mio_ust", f"/{card['id']}/close").status_code == 200
    assert post(client, world, "mio_ust", f"/{card['id']}/close").status_code == 409


def test_nothing_is_editable_after_sending(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    send(client, world, card["id"])
    response = client.patch(
        f"{API}/{card['id']}", headers=auth(world.users["mio_ust"]), json={"sections": {"note": "поздно"}}
    )
    assert response.status_code == 409
    assert post(client, world, "mio_ust", f"/{card['id']}/return", {"comment": "поздно"}).status_code == 409


# ---------------------------------------------------------------- visibility


def test_receiving_bodies_see_only_cards_sent_to_them(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    draft = create(client, world, obj)
    to_gask, to_law = create(client, world, obj), create(client, world, obj)
    send(client, world, to_gask["id"], "gask")
    send(client, world, to_law["id"], "law_enforcement")
    gask, law = auth(world.users["gask"]), auth(world.users["law"])

    gask_list = client.get(API, headers=gask).json()
    assert [item["id"] for item in gask_list["items"]] == [to_gask["id"]]
    assert gask_list["total"] == 1
    assert [item["id"] for item in client.get(API, headers=law).json()["items"]] == [to_law["id"]]

    assert client.get(f"{API}/{to_gask['id']}", headers=gask).status_code == 200
    assert client.get(f"{API}/{to_gask['id']}", headers=law).status_code == 404  # another body's card
    assert client.get(f"{API}/{draft['id']}", headers=gask).status_code == 404  # not sent yet
    assert client.get(f"{API}/{to_gask['id']}/pdf", headers=law).status_code == 404
    assert client.get(f"{API}?status=requires_confirmation", headers=gask).json()["items"] == []


def test_receiving_bodies_keep_seeing_responded_and_closed_cards(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    send(client, world, card["id"])
    post(client, world, "gask", f"/{card['id']}/response", {"response_text": "ok"})
    assert client.get(f"{API}/{card['id']}", headers=auth(world.users["gask"])).json()["status"] == "responded"
    post(client, world, "mio_ust", f"/{card['id']}/close")
    assert client.get(f"{API}/{card['id']}", headers=auth(world.users["gask"])).json()["status"] == "closed"


def test_receiving_bodies_are_limited_to_their_territory(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.semey), who="mio_semey")
    send(client, world, card["id"], who="mio_semey")
    assert client.get(f"{API}/{card['id']}", headers=auth(world.users["gask"])).status_code == 404  # gask: Ust only
    assert client.get(f"{API}/{card['id']}", headers=auth(world.users["law"])).status_code == 404  # addressed to gask
    assert [item["id"] for item in client.get(API, headers=auth(world.users["gask"])).json()["items"]] == []


def test_the_audit_trail_is_not_shown_to_receiving_bodies(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    send(client, world, card["id"])
    for who, expected in (("gask", 0), ("mio_ust", 2), ("admin", 2)):
        body = client.get(f"{API}/{card['id']}", headers=auth(world.users[who])).json()
        assert len(body["audit"]) == expected


def test_staff_visibility_follows_territory(client: TestClient, db: Session, world: World) -> None:
    ust, semey = (
        create(client, world, make_object(db, world.ust)),
        create(client, world, make_object(db, world.semey), who="mio_semey"),
    )

    def ids(who: str) -> set[int]:
        return {item["id"] for item in client.get(API, headers=auth(world.users[who])).json()["items"]}

    assert ids("mio_ust") == {ust["id"]}
    assert ids("mio_semey") == {semey["id"]}
    assert ids("mio_region") == ids("admin") == {ust["id"], semey["id"]}
    assert client.get(f"{API}/{semey['id']}", headers=auth(world.users["mio_ust"])).status_code == 404
    assert client.get(f"{API}/{semey['id']}/pdf", headers=auth(world.users["mio_ust"])).status_code == 404
    assert client.get(f"{API}/999999", headers=auth(world.users["admin"])).status_code == 404
    assert client.get(API).status_code == 401


def test_admin_reads_but_does_not_act(client: TestClient, db: Session, world: World) -> None:
    card = create(client, world, make_object(db, world.ust))
    admin = auth(world.users["admin"])
    assert client.get(f"{API}/{card['id']}", headers=admin).status_code == 200
    assert client.patch(f"{API}/{card['id']}", headers=admin, json={"review_days": 2}).status_code == 403


# ---------------------------------------------------------------- listing


def test_list_filters_and_overdue_flag(client: TestClient, db: Session, world: World) -> None:
    first, second = make_object(db, world.ust, "ЖК Первый", zone=Zone.red), make_object(db, world.ust, "ЖК Второй")
    sent_card, draft = create(client, world, first), create(client, world, second)
    send(client, world, sent_card["id"])
    headers = auth(world.users["mio_ust"])

    everything = client.get(API, headers=headers).json()
    assert [item["id"] for item in everything["items"]] == [draft["id"], sent_card["id"]]  # newest first
    row = next(item for item in everything["items"] if item["id"] == sent_card["id"])
    assert set(row) == {
        "id",
        "number",
        "object_id",
        "object_name",
        "zone",
        "status",
        "recipient",
        "due_date",
        "is_overdue",
        "created_at",
    }
    assert (row["object_name"], row["zone"], row["recipient"], row["is_overdue"]) == ("ЖК Первый", "red", "gask", False)

    assert [item["id"] for item in client.get(f"{API}?status=sent", headers=headers).json()["items"]] == [
        sent_card["id"]
    ]
    assert [item["id"] for item in client.get(f"{API}?object_id={second.id}", headers=headers).json()["items"]] == [
        draft["id"]
    ]
    assert client.get(f"{API}?limit=1&offset=1", headers=headers).json()["total"] == 2

    db.get_one(SignalCard, sent_card["id"]).due_date = datetime.now(UTC).date() - timedelta(days=2)
    db.flush()
    overdue = client.get(f"{API}/{sent_card['id']}", headers=headers).json()
    assert overdue["is_overdue"] is True
    assert next(i for i in client.get(API, headers=headers).json()["items"] if i["id"] == sent_card["id"])["is_overdue"]

    post(client, world, "gask", f"/{sent_card['id']}/response", {"response_text": "ok"})
    assert (
        client.get(f"{API}/{sent_card['id']}", headers=headers).json()["is_overdue"] is False
    )  # answered: not overdue


def test_due_date_equal_to_today_is_not_overdue(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    card = create(client, world, obj)
    send(client, world, card["id"])
    db.get_one(SignalCard, card["id"]).due_date = _local_today(db, obj)
    db.flush()
    assert client.get(f"{API}/{card['id']}", headers=auth(world.users["mio_ust"])).json()["is_overdue"] is False


# ---------------------------------------------------------------- e-mail


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], str, str, tuple[str, bytes, str] | None]]:
    sent: list[tuple[list[str], str, str, tuple[str, bytes, str] | None]] = []

    def send_email(to: list[str], subject: str, body: str, attachment: tuple[str, bytes, str] | None = None) -> bool:
        sent.append((to, subject, body, attachment))
        return True

    monkeypatch.setattr(router.mail, "smtp_enabled", lambda: True)
    monkeypatch.setattr(router.mail, "send_email", send_email)
    return sent


def test_sending_mails_the_pdf_to_the_addresses_of_the_body(
    client: TestClient, db: Session, world: World, smtp: list
) -> None:
    save_settings(
        db, {"recipient_emails": {"mio": [], "gask": ["gask@example.kz", "chief@example.kz"], "law_enforcement": []}}
    )
    card = create(client, world, make_object(db, world.ust))

    assert send(client, world, card["id"], "gask").status_code == 200

    [(to, subject, _body, attachment)] = smtp
    assert to == ["gask@example.kz", "chief@example.kz"]
    assert card["number"] in subject
    assert attachment is not None
    filename, data, mime_type = attachment
    assert (filename, mime_type) == (f"{card['number']}.pdf", "application/pdf")
    assert data.startswith(b"%PDF-")


def test_no_mail_without_addresses_or_smtp(
    client: TestClient, db: Session, world: World, smtp: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = create(client, world, make_object(db, world.ust))
    send(client, world, card["id"], "gask")  # SMTP on, but no addresses configured for the body
    assert smtp == []

    save_settings(db, {"recipient_emails": {"mio": [], "gask": ["g@example.kz"], "law_enforcement": []}})
    monkeypatch.setattr(router.mail, "smtp_enabled", lambda: False)
    other = create(client, world, make_object(db, world.ust, "ЖК Второй"))
    send(client, world, other["id"], "gask")
    assert smtp == []


def test_a_mail_problem_never_undoes_the_dispatch(
    client: TestClient, db: Session, world: World, smtp: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_settings(db, {"recipient_emails": {"mio": [], "gask": ["g@example.kz"], "law_enforcement": []}})

    def broken(*args: object, **kwargs: object) -> bytes:
        raise RuntimeError("renderer crashed")

    monkeypatch.setattr(pdf, "render_pdf", broken)
    card = create(client, world, make_object(db, world.ust))
    response = send(client, world, card["id"], "gask")
    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert smtp == []

"""Global search: objects, developers and signal cards inside the user's territory."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ConstructionObject, Developer, SignalCard
from app.models.enums import Recipient, SignalOrigin, SignalStatus
from tests.conftest import World, auth, make_object

API = "/api/v1/search"
EMPTY: dict[str, list[Any]] = {"objects": [], "developers": [], "signals": []}


def find(client: TestClient, world: World, who: str, q: str) -> dict[str, Any]:
    response = client.get(API, params={"q": q}, headers=auth(world.users[who]))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def add_developer(db: Session, bin_: str, name: str) -> Developer:
    developer = Developer(bin=bin_, name=name)
    db.add(developer)
    db.flush()
    return developer


def add_card(
    db: Session, obj: ConstructionObject, number: str, status: SignalStatus, recipient: Recipient | None = None
) -> SignalCard:
    card = SignalCard(number=number, object_id=obj.id, status=status, origin=SignalOrigin.manual, recipient=recipient)
    db.add(card)
    db.flush()
    return card


def test_finds_an_object_by_name_address_and_cadastral_number(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Алтын", address="ул. Абая 5", cadastral_number="05-123-456-789")

    for q, field in (("алтын", "name"), ("абая", "address"), ("05-123-456", "cadastral_number")):
        found = find(client, world, "mio_ust", q)["objects"]
        assert [(hit["id"], hit["match"]) for hit in found] == [(obj.id, field)]


def test_finds_by_developer_name_and_bin(client: TestClient, db: Session, world: World) -> None:
    developer = add_developer(db, "123456789012", "СтройИнвест")
    obj = make_object(db, world.ust, "ЖК Север", developer_id=developer.id)

    by_name = find(client, world, "mio_ust", "стройинв")
    assert [hit["id"] for hit in by_name["objects"]] == [obj.id]
    assert by_name["developers"] == [
        {"id": developer.id, "name": "СтройИнвест", "bin": "123456789012", "object_id": obj.id}
    ]

    by_bin = find(client, world, "mio_ust", "123456789012")
    assert [hit["id"] for hit in by_bin["objects"]] == [obj.id]
    assert by_bin["objects"][0]["match"] == "developer_bin"
    assert [hit["id"] for hit in by_bin["developers"]] == [developer.id]


def test_finds_a_card_by_number(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Карточка")
    card = add_card(db, obj, "SQ-2026-0012", SignalStatus.requires_confirmation)

    body = find(client, world, "mio_ust", "SQ-2026-0012")
    assert body["signals"] == [
        {"id": card.id, "number": "SQ-2026-0012", "object_name": "ЖК Карточка", "status": "requires_confirmation"}
    ]


def test_search_stays_inside_the_territory(client: TestClient, db: Session, world: World) -> None:
    developer = add_developer(db, "210987654321", "Семей Строй")
    make_object(db, world.semey, "ЖК Семей Парк", developer_id=developer.id)
    semey_obj = make_object(db, world.semey, "ЖК Семей Парк 2")
    add_card(db, semey_obj, "SQ-2026-0099", SignalStatus.sent, Recipient.gask)

    assert find(client, world, "mio_ust", "Семей Парк") == EMPTY
    assert find(client, world, "mio_ust", "SQ-2026-0099")["signals"] == []
    # A full BIN still finds the developer, but without a link to an object outside the scope.
    by_bin = find(client, world, "mio_ust", "210987654321")
    assert [(hit["name"], hit["object_id"]) for hit in by_bin["developers"]] == [("Семей Строй", None)]
    assert len(find(client, world, "mio_semey", "Семей Парк")["objects"]) == 2


def test_gask_sees_only_its_sent_cards_and_no_objects(client: TestClient, db: Session, world: World) -> None:
    obj = make_object(db, world.ust, "ЖК Адресат")
    add_card(db, obj, "SQ-2026-0201", SignalStatus.sent, Recipient.gask)
    add_card(db, obj, "SQ-2026-0202", SignalStatus.sent, Recipient.law_enforcement)
    add_card(db, obj, "SQ-2026-0203", SignalStatus.requires_confirmation, Recipient.gask)

    assert find(client, world, "gask", "Адресат") == EMPTY
    body = find(client, world, "gask", "SQ-2026")
    assert [hit["number"] for hit in body["signals"]] == ["SQ-2026-0201"]
    assert body["objects"] == []


def test_query_too_short_is_rejected(client: TestClient, world: World) -> None:
    response = client.get(API, params={"q": "а"}, headers=auth(world.users["mio_ust"]))
    assert response.status_code == 422


def test_like_wildcards_are_literal(client: TestClient, db: Session, world: World) -> None:
    make_object(db, world.ust, "ЖК Обычный")
    assert find(client, world, "mio_ust", "%%")["objects"] == []

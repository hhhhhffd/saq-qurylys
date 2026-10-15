import itertools
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ConstructionObject, Developer, LinkedEntity, SourceAccount
from app.models.enums import LinkedEntityKind, Platform, Zone
from app.modules.graph import service
from app.modules.settings.service import save_settings
from app.scope import TerritoryScope
from tests.conftest import World, auth, make_object
from tests.support_ads import add_ad

_bins = itertools.count(990000000001)


def make_developer(db: Session, name: str = "ТОО Тест", phones: list[str] | None = None) -> Developer:
    developer = Developer(bin=str(next(_bins)), name=name, phones=phones or [])
    db.add(developer)
    db.flush()
    return developer


def link(
    db: Session,
    kind: LinkedEntityKind,
    value: str,
    *,
    obj: ConstructionObject | None = None,
    dev: Developer | None = None,
) -> None:
    db.add(
        LinkedEntity(kind=kind, value=value, object_id=obj.id if obj else None, developer_id=dev.id if dev else None)
    )
    db.flush()


def get_graph(client: TestClient, user_key: str, world: World, **params: int) -> dict[str, Any]:
    response = client.get("/api/v1/graph", headers=auth(world.users[user_key]), params=params)
    assert response.status_code == 200, response.text
    graph: dict[str, Any] = response.json()
    return graph


def node_ids(graph: dict[str, Any], type_: str | None = None) -> set[str]:
    return {node["id"] for node in graph["nodes"] if type_ is None or node["type"] == type_}


def edges(graph: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]}


def test_every_kind_of_link_becomes_an_edge(client: TestClient, db: Session, world: World) -> None:
    developer = make_developer(db, "ТОО Акме", phones=["+7 700 000 90 01"])
    obj = make_object(db, world.ust, "ЖК Акме", developer_id=developer.id, zone=Zone.yellow, is_demo=True)
    link(db, LinkedEntityKind.phone, "+77000009002", obj=obj)
    link(db, LinkedEntityKind.ad_account, "https://instagram.com/Acme_Sales", obj=obj)
    link(db, LinkedEntityKind.website, "https://acme.example/flats", dev=developer)
    source = SourceAccount(platform=Platform.telegram, handle="Acme_News", object_id=obj.id, territory_id=world.ust.id)
    db.add(source)
    db.flush()
    ad = add_ad(
        db,
        world.ust,
        "Квартиры от Акме",
        object_id=obj.id,
        phones=["+77000009003"],
        links=["https://www.instagram.com/acme_sales/p/abc", "https://bit.ly/x", "https://acme.example/contacts"],
        source_account_id=source.id,
    )

    graph = get_graph(client, "admin", world)

    by_id = {node["id"]: node for node in graph["nodes"]}
    assert by_id[f"object:{obj.id}"] == {
        "id": f"object:{obj.id}",
        "type": "object",
        "label": "ЖК Акме",
        "ref_id": obj.id,
        "zone": "yellow",
        "is_demo": True,
        "platform": None,
    }
    assert by_id[f"developer:{developer.id}"]["label"] == "ТОО Акме"
    assert by_id["phone:+77000009001"]["label"] == "+77000009001"  # a developer phone is normalized to E.164
    assert by_id["account:instagram/acme_sales"]["label"] == "@acme_sales"
    assert by_id["account:instagram/acme_sales"]["platform"] == "instagram"
    assert by_id["account:telegram/acme_news"]["label"] == "@acme_news"
    assert by_id["account:website/acme.example"]["label"] == "acme.example"
    assert by_id[f"ad:{ad.id}"]["type"] == "ad" and by_id[f"ad:{ad.id}"]["label"] == "Квартиры от Акме"
    assert not any("bit.ly" in key for key in by_id)  # a link to a site nobody owns is not an account

    developer_key, object_key, ad_key = f"developer:{developer.id}", f"object:{obj.id}", f"ad:{ad.id}"
    assert edges(graph) == {
        (developer_key, object_key, "developer_object"),
        (developer_key, "phone:+77000009001", "owner_phone"),
        (object_key, "phone:+77000009002", "owner_phone"),
        (object_key, "account:instagram/acme_sales", "owner_account"),
        (developer_key, "account:website/acme.example", "owner_account"),
        (object_key, "account:telegram/acme_news", "owner_account"),
        (ad_key, object_key, "ad_object"),
        (ad_key, "phone:+77000009003", "ad_phone"),
        (ad_key, "account:telegram/acme_news", "ad_account"),
        (ad_key, "account:instagram/acme_sales", "ad_account"),
        (ad_key, "account:website/acme.example", "ad_account"),
    }
    assert graph["findings"] == [] and graph["truncated"] is False


def test_a_phone_or_account_is_one_node_however_it_is_written(client: TestClient, db: Session, world: World) -> None:
    first = make_object(db, world.ust, "ЖК Один")
    second = make_object(db, world.ust, "ЖК Два")
    link(db, LinkedEntityKind.phone, "+77000009101", obj=first)
    add_ad(db, world.ust, "Звоните", object_id=second.id, phones=["+77000009101"], links=["t.me/Shared_Chan"])
    link(db, LinkedEntityKind.ad_account, "https://t.me/shared_chan", obj=first)

    graph = get_graph(client, "admin", world)

    assert node_ids(graph, "phone") == {"phone:+77000009101"}
    assert node_ids(graph, "account") == {"account:telegram/shared_chan"}


def test_isolated_nodes_are_left_out_of_the_whole_view(client: TestClient, db: Session, world: World) -> None:
    make_object(db, world.ust, "ЖК Одиночка")
    developer = make_developer(db)
    obj = make_object(db, world.ust, "ЖК Связанный", developer_id=developer.id)

    graph = get_graph(client, "admin", world)

    assert node_ids(graph) == {f"developer:{developer.id}", f"object:{obj.id}"}


def test_empty_scope_gives_an_empty_graph(client: TestClient, world: World) -> None:
    assert get_graph(client, "admin", world) == {"nodes": [], "edges": [], "findings": [], "truncated": False}


@pytest.fixture
def chain(db: Session, world: World) -> dict[str, ConstructionObject | Developer]:
    """o1 (d1) - d1 - o2 - phone P - o3 (d2) - d2 - o4 - phone Q - o5 (d3). Q is three hops from o1."""
    d1, d2, d3 = (make_developer(db, f"ТОО {i}") for i in (1, 2, 3))
    o1, o2 = (make_object(db, world.ust, f"ЖК {i}", developer_id=d1.id) for i in (1, 2))
    o3, o4 = (make_object(db, world.ust, f"ЖК {i}", developer_id=d2.id) for i in (3, 4))
    o5 = make_object(db, world.ust, "ЖК 5", developer_id=d3.id)
    lonely = make_object(db, world.ust, "ЖК Одиночка")
    link(db, LinkedEntityKind.phone, "+77000009201", obj=o2)
    link(db, LinkedEntityKind.phone, "+77000009201", obj=o3)
    link(db, LinkedEntityKind.phone, "+77000009202", obj=o4)
    link(db, LinkedEntityKind.phone, "+77000009202", obj=o5)
    return {"d1": d1, "d2": d2, "d3": d3, "o1": o1, "o2": o2, "o3": o3, "o4": o4, "o5": o5, "lonely": lonely}


def test_object_view_is_the_two_hop_neighbourhood(
    client: TestClient, world: World, chain: dict[str, ConstructionObject | Developer]
) -> None:
    graph = get_graph(client, "admin", world, object_id=chain["o1"].id)

    # o1 -> its developer -> that developer's other object -> its phone -> whoever holds it, with their developers
    assert node_ids(graph, "object") == {f"object:{chain[key].id}" for key in ("o1", "o2", "o3", "o4")}
    assert node_ids(graph, "developer") == {f"developer:{chain[key].id}" for key in ("d1", "d2")}
    assert node_ids(graph, "phone") == {"phone:+77000009201"}  # the phone one hop further stays out
    assert f"object:{chain['o5'].id}" not in node_ids(graph)


def test_developer_view_starts_from_the_developer(
    client: TestClient, world: World, chain: dict[str, ConstructionObject | Developer]
) -> None:
    graph = get_graph(client, "admin", world, developer_id=chain["d2"].id)

    assert node_ids(graph, "developer") == {f"developer:{chain[key].id}" for key in ("d1", "d2", "d3")}
    assert node_ids(graph, "phone") == {"phone:+77000009201", "phone:+77000009202"}


def test_an_object_without_links_is_still_shown_when_asked_for(
    client: TestClient, world: World, chain: dict[str, ConstructionObject | Developer]
) -> None:
    graph = get_graph(client, "admin", world, object_id=chain["lonely"].id)

    assert node_ids(graph) == {f"object:{chain['lonely'].id}"} and graph["edges"] == []


def test_territory_view_narrows_the_whole_scope(client: TestClient, db: Session, world: World) -> None:
    ust_developer, semey_developer = make_developer(db), make_developer(db)
    ust_object = make_object(db, world.ust, "ЖК Усть", developer_id=ust_developer.id)
    semey_object = make_object(db, world.semey, "ЖК Семей", developer_id=semey_developer.id)

    graph = get_graph(client, "admin", world, territory_id=world.semey.id)
    assert node_ids(graph, "object") == {f"object:{semey_object.id}"}

    region = get_graph(client, "admin", world, territory_id=world.region.id)
    assert node_ids(region, "object") == {f"object:{ust_object.id}", f"object:{semey_object.id}"}


def test_scope_restricts_the_graph_and_its_findings(client: TestClient, db: Session, world: World) -> None:
    d_ust, d_semey = make_developer(db), make_developer(db)
    o_ust = make_object(db, world.ust, "ЖК Усть", developer_id=d_ust.id)
    o_semey = make_object(db, world.semey, "ЖК Семей", developer_id=d_semey.id)
    link(db, LinkedEntityKind.phone, "+77000009301", obj=o_ust)
    link(db, LinkedEntityKind.phone, "+77000009301", obj=o_semey)
    ad_semey = add_ad(db, world.semey, "Семей", object_id=o_semey.id)

    everything = get_graph(client, "admin", world)
    assert [f["value"] for f in everything["findings"]] == ["+77000009301"]

    mine = get_graph(client, "mio_ust", world)
    assert node_ids(mine, "object") == {f"object:{o_ust.id}"}
    assert node_ids(mine, "developer") == {f"developer:{d_ust.id}"}
    assert f"ad:{ad_semey.id}" not in node_ids(mine)
    assert mine["findings"] == []  # the other developer is invisible to this user, so is what ties them together


def test_objects_and_developers_outside_the_scope_are_not_found(client: TestClient, db: Session, world: World) -> None:
    developer = make_developer(db)
    foreign = make_object(db, world.semey, "ЖК Семей", developer_id=developer.id)
    headers = auth(world.users["mio_ust"])

    assert client.get("/api/v1/graph", headers=headers, params={"object_id": foreign.id}).status_code == 404
    assert client.get("/api/v1/graph", headers=headers, params={"developer_id": developer.id}).status_code == 404


def test_only_one_focus_parameter_is_accepted(client: TestClient, world: World) -> None:
    response = client.get(
        "/api/v1/graph", headers=auth(world.users["admin"]), params={"object_id": 1, "developer_id": 2}
    )
    assert response.status_code == 422 and response.json()["detail"]["code"] == "validation_error"


def test_only_staff_may_read_the_graph(client: TestClient, world: World) -> None:
    assert client.get("/api/v1/graph").status_code == 401
    assert client.get("/api/v1/graph", headers=auth(world.users["gask"])).status_code == 403
    assert client.get("/api/v1/graph", headers=auth(world.users["mio_ust"])).status_code == 200


def test_publications_come_from_the_longer_of_ninety_days_and_the_ad_window(
    client: TestClient, db: Session, world: World
) -> None:
    obj = make_object(db, world.ust, "ЖК Окно")
    now = datetime.now(UTC)
    recent = add_ad(db, world.ust, "Свежая", object_id=obj.id, published_at=now - timedelta(days=60))
    old = add_ad(db, world.ust, "Старая", object_id=obj.id, published_at=now - timedelta(days=100))

    assert node_ids(get_graph(client, "admin", world), "ad") == {
        f"ad:{recent.id}"
    }  # 30-day window, 60 days still count

    save_settings(db, {"ad_window_days": 120})
    assert node_ids(get_graph(client, "admin", world), "ad") == {f"ad:{recent.id}", f"ad:{old.id}"}


# ---------------------------------------------------------------- findings


def test_a_phone_shared_by_developers_directly_or_through_publications_is_a_finding(
    client: TestClient, db: Session, world: World
) -> None:
    d1 = make_developer(db, phones=["+77000009401"])  # the phone is the developer's own
    d2 = make_developer(db)
    d3 = make_developer(db)
    o1 = make_object(db, world.ust, "ЖК 1", developer_id=d1.id)
    o2 = make_object(db, world.ust, "ЖК 2", developer_id=d2.id)
    o3 = make_object(db, world.ust, "ЖК 3", developer_id=d3.id)
    link(db, LinkedEntityKind.phone, "+77000009401", obj=o2)
    add_ad(db, world.ust, "Звоните", object_id=o3.id, phones=["+77000009401"])  # only a publication ties o3

    [finding] = get_graph(client, "admin", world)["findings"]

    assert finding == {
        "kind": "shared_phone",
        "value": "+77000009401",
        "label": "Один телефон у 3 застройщиков",
        "developer_ids": sorted([d1.id, d2.id, d3.id]),
        "object_ids": sorted([o1.id, o2.id, o3.id]),  # the objects of a developer holding the phone count too
    }


def test_a_shared_account_is_a_finding(client: TestClient, db: Session, world: World) -> None:
    d1, d2 = make_developer(db), make_developer(db)
    o1 = make_object(db, world.ust, "ЖК 1", developer_id=d1.id)
    o2 = make_object(db, world.ust, "ЖК 2", developer_id=d2.id)
    link(db, LinkedEntityKind.ad_account, "https://instagram.com/agency_x", obj=o1)
    add_ad(db, world.ust, "Агентство", object_id=o2.id, links=["https://instagram.com/agency_x"])

    [finding] = get_graph(client, "admin", world)["findings"]

    assert finding["kind"] == "shared_account" and finding["value"] == "instagram/agency_x"
    assert finding["label"] == "Один аккаунт у 2 застройщиков"
    assert finding["developer_ids"] == sorted([d1.id, d2.id])


def test_one_developer_behind_many_objects_is_not_a_finding(client: TestClient, db: Session, world: World) -> None:
    developer = make_developer(db)
    for number in (1, 2):
        obj = make_object(db, world.ust, f"ЖК {number}", developer_id=developer.id)
        link(db, LinkedEntityKind.phone, "+77000009501", obj=obj)

    graph = get_graph(client, "admin", world)

    assert graph["findings"] == [] and "phone:+77000009501" in node_ids(graph)


def test_a_saved_search_of_an_aggregator_is_not_an_account_that_ties_developers(
    client: TestClient, db: Session, world: World
) -> None:
    search = SourceAccount(platform=Platform.aggregator, handle="новостройки", territory_id=world.ust.id)
    db.add(search)
    db.flush()
    for number in (1, 2):
        developer = make_developer(db)
        obj = make_object(db, world.ust, f"ЖК {number}", developer_id=developer.id)
        add_ad(db, world.ust, "Объявление", object_id=obj.id, source_account_id=search.id)

    graph = get_graph(client, "admin", world)

    assert "account:aggregator/новостройки" in node_ids(graph) and graph["findings"] == []


def test_findings_are_ordered_by_the_number_of_developers(client: TestClient, db: Session, world: World) -> None:
    for phone, count in (("+77000009601", 2), ("+77000009602", 4)):
        for number in range(count):
            obj = make_object(db, world.ust, f"ЖК {phone}-{number}", developer_id=make_developer(db).id)
            link(db, LinkedEntityKind.phone, phone, obj=obj)

    findings = get_graph(client, "admin", world)["findings"]

    assert [(f["value"], len(f["developer_ids"])) for f in findings] == [("+77000009602", 4), ("+77000009601", 2)]


@pytest.mark.parametrize(
    ("count", "word"), [(2, "застройщиков"), (5, "застройщиков"), (11, "застройщиков"), (21, "застройщика")]
)
def test_the_label_agrees_with_the_number(count: int, word: str) -> None:
    assert service._developers_phrase(count) == word


# ---------------------------------------------------------------- truncation


def test_a_large_graph_is_cut_to_the_limit_keeping_findings(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "MAX_NODES", 6)
    for number in range(5):  # five pairs developer-object with no finding
        make_object(db, world.ust, f"ЖК пара {number}", developer_id=make_developer(db).id)
    tied = [make_object(db, world.ust, f"ЖК сеть {n}", developer_id=make_developer(db).id) for n in (1, 2)]
    for obj in tied:
        link(db, LinkedEntityKind.phone, "+77000009701", obj=obj)

    graph = get_graph(client, "admin", world)

    assert graph["truncated"] is True and len(graph["nodes"]) == 6
    assert {"phone:+77000009701", *(f"object:{obj.id}" for obj in tied)} <= node_ids(graph)
    assert [f["value"] for f in graph["findings"]] == ["+77000009701"]
    kept = node_ids(graph)
    assert graph["edges"] and all(e["source"] in kept and e["target"] in kept for e in graph["edges"])


def test_a_focused_view_keeps_its_seed_when_cut(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "MAX_NODES", 3)
    developer = make_developer(db)
    objects = [make_object(db, world.ust, f"ЖК {n}", developer_id=developer.id) for n in range(5)]

    graph = get_graph(client, "admin", world, object_id=objects[0].id)

    assert graph["truncated"] is True and len(graph["nodes"]) == 3
    assert {f"object:{objects[0].id}", f"developer:{developer.id}"} <= node_ids(graph)


def test_a_graph_within_the_limit_is_not_truncated(client: TestClient, db: Session, world: World) -> None:
    make_object(db, world.ust, "ЖК", developer_id=make_developer(db).id)

    assert get_graph(client, "admin", world)["truncated"] is False


def test_territory_scope_of_a_region_includes_its_cities(db: Session, world: World) -> None:
    whole = service.territory_scope(db, TerritoryScope(ids=None), world.region.id)
    assert whole.ids == {world.region.id, world.ust.id, world.semey.id}
    narrowed = service.territory_scope(db, TerritoryScope(ids=frozenset({world.ust.id})), world.region.id)
    assert narrowed.ids == {world.ust.id}

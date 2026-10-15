"""Endpoints of the sources screen: collector states, «Собрать сейчас» and the search address of an aggregator."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, SourceAccount
from app.models.enums import Platform
from tests.conftest import World, auth, make_object

ACCOUNTS = "/api/v1/source-accounts"
OLX_SEARCH = "https://www.olx.kz/nedvizhimost/q-novostroyka/"
KRISHA_SEARCH = "https://krisha.kz/prodazha/kvartiry/ust-kamenogorsk/?das[novostroiki]=1"


@pytest.fixture(autouse=True)
def collectors_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whatever `.env` says, every test starts with all collectors off."""
    settings = get_settings()
    for name in ("collect_telegram_enabled", "collect_olx_enabled", "collect_krisha_enabled"):
        monkeypatch.setattr(settings, name, False)
    monkeypatch.setattr(settings, "instagram_graph_token", "")
    monkeypatch.setattr(settings, "instagram_graph_user_id", "")


def switch_on(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    for name in names:
        monkeypatch.setattr(get_settings(), name, True)


def add_account(db: Session, world: World, platform: Platform, handle: str, url: str | None = None) -> SourceAccount:
    account = SourceAccount(platform=platform, handle=handle, url=url, territory_id=world.ust.id)
    db.add(account)
    db.flush()
    return account


# ---------------------------------------------------------------- collector states


def test_collector_states_follow_the_settings(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth(world.users["mio_ust"])

    def states() -> list[dict[str, Any]]:
        response = client.get(f"{ACCOUNTS}/collectors", headers=headers)
        assert response.status_code == 200
        body: list[dict[str, Any]] = response.json()
        return body

    off = {"olx": False, "krisha": False}
    assert states() == [
        {"platform": "instagram", "enabled": False, "sources": {}},
        {"platform": "telegram", "enabled": False, "sources": {}},
        {"platform": "aggregator", "enabled": False, "sources": off},
    ]

    switch_on(monkeypatch, "collect_telegram_enabled", "collect_krisha_enabled")
    monkeypatch.setattr(get_settings(), "instagram_graph_token", "token")
    assert [(item["platform"], item["enabled"]) for item in states()] == [
        ("instagram", False),  # a token alone is not enough: the user id is needed to call the API
        ("telegram", True),
        ("aggregator", True),
    ]
    assert states()[2]["sources"] == {"olx": False, "krisha": True}
    monkeypatch.setattr(get_settings(), "instagram_graph_user_id", "17841400000000099")
    assert states()[0]["enabled"] is True


def test_collector_states_are_for_staff(client: TestClient, world: World) -> None:
    assert client.get(f"{ACCOUNTS}/collectors", headers=auth(world.users["gask"])).status_code == 403
    assert client.get(f"{ACCOUNTS}/collectors").status_code == 401


# ---------------------------------------------------------------- collect now


def test_collect_now_queues_the_task_and_is_audited(
    client: TestClient,
    db: Session,
    world: World,
    sent_tasks: list[tuple[str, tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    switch_on(monkeypatch, "collect_telegram_enabled")
    account = add_account(db, world, Platform.telegram, "alatau_demo")

    response = client.post(f"{ACCOUNTS}/{account.id}/collect", headers=auth(world.users["mio_ust"]))

    assert response.status_code == 202 and response.json() == {"queued": True}
    assert sent_tasks == [("collect.source", (account.id,))]
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "source_account.collect")).one()
    assert (entry.user_id, entry.entity_type, entry.entity_id) == (
        world.users["mio_ust"].id,
        "source_account",
        account.id,
    )


def test_collect_now_is_refused_while_the_collector_is_off(
    client: TestClient, db: Session, world: World, sent_tasks: list[tuple[str, tuple[object, ...]]]
) -> None:
    account = add_account(db, world, Platform.telegram, "alatau_demo")

    response = client.post(f"{ACCOUNTS}/{account.id}/collect", headers=auth(world.users["mio_ust"]))

    assert response.status_code == 409 and response.json()["detail"]["code"] == "collector_disabled"
    assert sent_tasks == []
    assert db.scalars(select(AuditLog).where(AuditLog.action == "source_account.collect")).all() == []


def test_an_aggregator_search_needs_the_collector_of_its_own_site(
    client: TestClient,
    db: Session,
    world: World,
    sent_tasks: list[tuple[str, tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    switch_on(monkeypatch, "collect_olx_enabled")
    olx = add_account(db, world, Platform.aggregator, "olx search", OLX_SEARCH)
    krisha = add_account(db, world, Platform.aggregator, "krisha search", KRISHA_SEARCH)
    headers = auth(world.users["mio_ust"])

    assert client.post(f"{ACCOUNTS}/{olx.id}/collect", headers=headers).status_code == 202
    refused = client.post(f"{ACCOUNTS}/{krisha.id}/collect", headers=headers)

    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "collector_disabled"
    assert sent_tasks == [("collect.source", (olx.id,))]


def test_collect_now_respects_roles_and_territory(
    client: TestClient,
    db: Session,
    world: World,
    sent_tasks: list[tuple[str, tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    switch_on(monkeypatch, "collect_telegram_enabled")
    account = add_account(db, world, Platform.telegram, "alatau_demo")
    url = f"{ACCOUNTS}/{account.id}/collect"

    assert client.post(url, headers=auth(world.users["mio_semey"])).status_code == 404
    assert client.post(url, headers=auth(world.users["gask"])).status_code == 403
    assert client.post(url).status_code == 401
    assert client.post(f"{ACCOUNTS}/0/collect", headers=auth(world.users["admin"])).status_code == 404
    assert sent_tasks == []
    assert client.post(url, headers=auth(world.users["admin"])).status_code == 202


def test_collect_now_answers_503_when_the_queue_is_down(
    client: TestClient, db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("broker is down")

    switch_on(monkeypatch, "collect_telegram_enabled", "events_enabled")
    monkeypatch.setattr("app.events.celery_app.send_task", down)
    account = add_account(db, world, Platform.telegram, "alatau_demo")

    response = client.post(f"{ACCOUNTS}/{account.id}/collect", headers=auth(world.users["mio_ust"]))

    assert response.status_code == 503 and response.json()["detail"]["code"] == "queue_unavailable"
    assert db.scalars(select(AuditLog).where(AuditLog.action == "source_account.collect")).all() == []


# ---------------------------------------------------------------- aggregator accounts


def test_an_aggregator_account_needs_a_search_address_on_a_supported_site(client: TestClient, world: World) -> None:
    headers = auth(world.users["mio_ust"])

    def create(**body: object) -> Any:
        return client.post(ACCOUNTS, headers=headers, json={"platform": "aggregator", **body})

    for body in (
        {"handle": "Без адреса"},
        {"handle": "Чужой сайт", "url": "https://example.com/search?q=zhk"},
        {"handle": "Не http", "url": "ftp://olx.kz/q-zhk/"},
        {"handle": "Мобильный", "url": "https://m.olx.kz/q-zhk/"},
        {"handle": "Запрещено robots", "url": "https://krisha.kz/prodazha/kvartiry/?raion=3"},
    ):
        response = create(**body)
        assert response.status_code == 422, body
        assert response.json()["detail"]["code"] == "invalid_source_url"

    created = create(handle="Новостройки OLX", url=OLX_SEARCH)
    assert created.status_code == 201, created.text
    assert created.json()["handle"] == "новостройки olx" and created.json()["url"] == OLX_SEARCH
    assert create(handle="Новостройки OLX", url=KRISHA_SEARCH).status_code == 409  # the label is unique
    assert create(url="https://www.krisha.kz/prodazha/kvartiry/almaty/").status_code == 201


def test_a_search_without_a_label_is_named_by_its_address(client: TestClient, world: World) -> None:
    headers = auth(world.users["mio_ust"])
    first = client.post(ACCOUNTS, headers=headers, json={"platform": "aggregator", "url": KRISHA_SEARCH})
    second = client.post(
        ACCOUNTS, headers=headers, json={"platform": "aggregator", "url": "https://krisha.kz/prodazha/kvartiry/semey/"}
    )

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["handle"] == "krisha.kz/prodazha/kvartiry/ust-kamenogorsk?das[novostroiki]=1"
    assert second.json()["handle"] == "krisha.kz/prodazha/kvartiry/semey"
    # The same search again is the same name: not added twice.
    again = client.post(ACCOUNTS, headers=headers, json={"platform": "aggregator", "url": KRISHA_SEARCH})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "source_account_exists"


def test_changing_the_search_address_of_an_aggregator_account_is_checked(client: TestClient, world: World) -> None:
    headers = auth(world.users["mio_ust"])
    account = client.post(
        ACCOUNTS, headers=headers, json={"platform": "aggregator", "handle": "poisk", "url": OLX_SEARCH}
    ).json()
    url = f"{ACCOUNTS}/{account['id']}"

    for bad in ("https://example.com/", None):
        response = client.patch(url, headers=headers, json={"url": bad})
        assert response.status_code == 422 and response.json()["detail"]["code"] == "invalid_source_url"
    ok = client.patch(url, headers=headers, json={"url": KRISHA_SEARCH, "is_watched": False})
    assert ok.status_code == 200 and ok.json()["url"] == KRISHA_SEARCH
    # Other platforms keep taking any address.
    other = client.post(
        ACCOUNTS, headers=headers, json={"platform": "website", "handle": "site", "url": "https://example.com/"}
    )
    assert other.status_code == 201


def test_accounts_of_other_platforms_are_created_as_before(client: TestClient, world: World) -> None:
    headers = auth(world.users["mio_ust"])
    telegram = client.post(
        ACCOUNTS, headers=headers, json={"platform": "telegram", "url": "https://t.me/s/Alatau_News"}
    )
    instagram = client.post(ACCOUNTS, headers=headers, json={"platform": "instagram", "handle": "@Alatau_ZHK"})

    assert telegram.json()["handle"] == "alatau_news" and instagram.json()["handle"] == "alatau_zhk"
    assert telegram.json()["last_error"] is None and telegram.json()["last_error_at"] is None


def test_a_saved_search_of_an_aggregator_cannot_be_bound_to_an_object(
    client: TestClient, db: Session, world: World
) -> None:
    headers = auth(world.users["mio_ust"])
    obj = make_object(db, world.ust, "Жилой комплекс Нур Плаза")

    refused = client.post(
        ACCOUNTS,
        headers=headers,
        json={"platform": "aggregator", "handle": "poisk", "url": OLX_SEARCH, "object_id": obj.id},
    )

    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "aggregator_object_not_allowed"
    assert db.scalars(select(SourceAccount).where(SourceAccount.platform == Platform.aggregator)).all() == []
    created = client.post(
        ACCOUNTS, headers=headers, json={"platform": "aggregator", "handle": "poisk", "url": OLX_SEARCH}
    )
    assert created.status_code == 201 and created.json()["object_id"] is None
    url = f"{ACCOUNTS}/{created.json()['id']}"
    patched = client.patch(url, headers=headers, json={"object_id": obj.id})
    assert patched.status_code == 422 and patched.json()["detail"]["code"] == "aggregator_object_not_allowed"
    # Clearing is allowed (a search bound before this rule), and so is an update that leaves the object alone.
    assert client.patch(url, headers=headers, json={"object_id": None, "is_watched": False}).status_code == 200


def test_accounts_of_a_single_publisher_are_still_bound_to_an_object(
    client: TestClient, db: Session, world: World
) -> None:
    headers = auth(world.users["mio_ust"])
    obj = make_object(db, world.ust, "Жилой комплекс Нур Плаза")

    created = client.post(
        ACCOUNTS, headers=headers, json={"platform": "telegram", "handle": "nur_plaza", "object_id": obj.id}
    )

    assert created.status_code == 201 and created.json()["object_id"] == obj.id

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, DismissedSourceSuggestion, SourceAccount
from app.models.enums import Platform, Zone
from tests.conftest import World, auth, make_object
from tests.support_ads import add_ad


def suggestions(client: TestClient, world: World, user_key: str = "admin") -> list[dict[str, Any]]:
    response = client.get("/api/v1/source-suggestions", headers=auth(world.users[user_key]))
    assert response.status_code == 200, response.text
    rows: list[dict[str, Any]] = response.json()
    return rows


def test_accounts_named_in_links_are_suggested_with_their_profile_url(
    client: TestClient, db: Session, world: World
) -> None:
    obj = make_object(db, world.ust, "ЖК Ссылки")
    seen = datetime.now(UTC) - timedelta(days=2)
    add_ad(
        db,
        world.ust,
        "Пост",
        object_id=obj.id,
        published_at=seen,
        links=[
            "https://www.instagram.com/Some_Agency/p/abc/",
            "t.me/s/news_channel",
            "https://www.tiktok.com/@dance.team/video/123",
            "https://example.org/page",  # not a social profile
            "https://t.me/share/url?url=x",  # a Telegram service path, not a channel
            "https://instagram.com/p/xyz",  # a post without the author
        ],
    )

    rows = {(row["platform"], row["handle"]): row for row in suggestions(client, world)}

    assert set(rows) == {("instagram", "some_agency"), ("telegram", "news_channel"), ("tiktok", "dance.team")}
    instagram = rows[("instagram", "some_agency")]
    assert instagram["url"] == "https://www.instagram.com/some_agency/"
    assert rows[("telegram", "news_channel")]["url"] == "https://t.me/news_channel"
    assert rows[("tiktok", "dance.team")]["url"] == "https://www.tiktok.com/@dance.team"
    assert instagram["posts_count"] == 1 and instagram["object_ids"] == [obj.id]
    assert datetime.fromisoformat(instagram["last_seen_at"]) == seen


def test_known_and_dismissed_accounts_are_not_suggested(client: TestClient, db: Session, world: World) -> None:
    db.add(SourceAccount(platform=Platform.instagram, handle="Watched_One", territory_id=world.ust.id))
    db.add(DismissedSourceSuggestion(platform=Platform.telegram, handle="declined_chan"))
    db.flush()
    add_ad(
        db,
        world.ust,
        "Пост",
        links=[
            "https://instagram.com/watched_one",  # the same account, other letter case
            "https://t.me/declined_chan",
            "https://t.me/watched_one",  # the same handle on another platform is another account
            "https://instagram.com/fresh_one",
        ],
    )

    assert [(row["platform"], row["handle"]) for row in suggestions(client, world)] == [
        ("instagram", "fresh_one"),
        ("telegram", "watched_one"),
    ]


def test_an_account_is_counted_once_per_post(client: TestClient, db: Session, world: World) -> None:
    add_ad(db, world.ust, "Пост", links=["https://instagram.com/twice", "https://www.instagram.com/Twice/"])
    add_ad(db, world.ust, "Другой пост", links=["https://instagram.com/twice"])

    [row] = suggestions(client, world)

    assert row["posts_count"] == 2


def test_suggestions_are_ranked_by_posts_then_by_risky_zone_then_by_recency(
    client: TestClient, db: Session, world: World
) -> None:
    red = make_object(db, world.ust, "ЖК Красный", zone=Zone.red)
    yellow = make_object(db, world.ust, "ЖК Жёлтый", zone=Zone.yellow)
    green = make_object(db, world.ust, "ЖК Зелёный", zone=Zone.green)
    now = datetime.now(UTC)
    posts = {
        "many": (green, 3, 5),  # the most posts wins whatever the zones are
        "on_red": (red, 2, 6),
        "on_yellow": (yellow, 2, 6),
        "on_green_new": (green, 2, 1),
        "on_green_old": (green, 2, 9),
        "single": (red, 1, 1),
    }
    for handle, (obj, count, days_ago) in posts.items():
        for _ in range(count):
            add_ad(
                db,
                world.ust,
                "Пост",
                object_id=obj.id,
                links=[f"https://instagram.com/{handle}"],
                published_at=now - timedelta(days=days_ago),
            )

    assert [row["handle"] for row in suggestions(client, world)] == [
        "many",
        "on_red",
        "on_yellow",
        "on_green_new",
        "on_green_old",
        "single",
    ]


def test_suggestions_follow_the_scope_and_the_window(client: TestClient, db: Session, world: World) -> None:
    add_ad(db, world.ust, "Пост", links=["https://instagram.com/mine"])
    add_ad(db, world.semey, "Пост", links=["https://instagram.com/theirs"])
    add_ad(
        db,
        world.ust,
        "Давний пост",
        links=["https://instagram.com/forgotten"],
        published_at=datetime.now(UTC) - timedelta(days=120),
    )

    assert [row["handle"] for row in suggestions(client, world, "mio_ust")] == ["mine"]
    assert {row["handle"] for row in suggestions(client, world, "admin")} == {"mine", "theirs"}


def test_only_staff_read_suggestions(client: TestClient, world: World) -> None:
    assert client.get("/api/v1/source-suggestions").status_code == 401
    assert client.get("/api/v1/source-suggestions", headers=auth(world.users["gask"])).status_code == 403


def test_accepting_a_suggestion_through_the_source_account_endpoint_removes_it(
    client: TestClient, db: Session, world: World
) -> None:
    add_ad(db, world.ust, "Пост", links=["https://instagram.com/to_accept"])
    [row] = suggestions(client, world)

    created = client.post(
        "/api/v1/source-accounts",
        headers=auth(world.users["mio_ust"]),
        json={"platform": row["platform"], "url": row["url"]},
    )

    assert created.status_code == 201 and created.json()["handle"] == "to_accept"
    assert suggestions(client, world) == []


def test_dismissing_hides_the_suggestion_and_is_repeatable(client: TestClient, db: Session, world: World) -> None:
    add_ad(db, world.ust, "Пост", links=["https://instagram.com/noise", "https://instagram.com/signal"])
    headers = auth(world.users["mio_ust"])

    for _ in range(2):
        response = client.post(
            "/api/v1/source-suggestions/dismiss", headers=headers, json={"platform": "instagram", "handle": " @Noise "}
        )
        assert response.status_code == 204

    assert [row["handle"] for row in suggestions(client, world)] == ["signal"]
    [dismissed] = db.scalars(select(DismissedSourceSuggestion)).all()
    assert (dismissed.platform, dismissed.handle, dismissed.dismissed_by) == (
        Platform.instagram,
        "noise",
        world.users["mio_ust"].id,
    )
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "source_suggestion.dismiss")).all()
    assert len(audit) == 1  # the repeat changed nothing
    assert audit[0].user_id == world.users["mio_ust"].id
    assert audit[0].after == {"platform": "instagram", "handle": "noise"}


def test_dismiss_is_for_staff_and_needs_a_handle(client: TestClient, world: World) -> None:
    body = {"platform": "instagram", "handle": "x"}
    assert client.post("/api/v1/source-suggestions/dismiss", json=body).status_code == 401
    assert (
        client.post("/api/v1/source-suggestions/dismiss", headers=auth(world.users["gask"]), json=body).status_code
        == 403
    )
    headers = auth(world.users["admin"])
    assert (
        client.post(
            "/api/v1/source-suggestions/dismiss", headers=headers, json={"platform": "instagram", "handle": "@"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/source-suggestions/dismiss", headers=headers, json={"platform": "nowhere", "handle": "x"}
        ).status_code
        == 422
    )

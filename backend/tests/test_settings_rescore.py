"""A change of a setting the risk calculation reads rescores every object (like a change of a factor weight)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import World, auth, make_object

URL = "/api/v1/settings"
SCORING_CHANGES: list[dict[str, Any]] = [
    {"ad_window_days": 14},
    {"readiness_gap_pp": 15},
    {"stalled_days": 10},
    {"significant_delay_days": 60},
    {"zone_yellow_min": 20},
    {"zone_red_min": 70},
]


def recalc_events(sent_tasks: list) -> set[int]:
    return {args[0] for name, args in sent_tasks if name == "risk.recalc_object"}


@pytest.mark.parametrize("change", SCORING_CHANGES, ids=lambda change: next(iter(change)))
def test_a_scoring_setting_rescores_all_objects(
    client: TestClient, db: Session, world: World, sent_tasks: list, change: dict[str, Any]
) -> None:
    ust, semey = make_object(db, world.ust), make_object(db, world.semey, "ЖК Семей")
    sent_tasks.clear()

    response = client.put(URL, headers=auth(world.users["admin"]), json=change)

    assert response.status_code == 200, response.text
    assert recalc_events(sent_tasks) == {ust.id, semey.id}


@pytest.mark.parametrize(
    "change",
    [
        {"review_days": 3},
        {"recheck_after_days": 5},
        {"link_confidence_threshold": 0.9},
        {"green_interval_days": 20},
        {"yellow_interval_days": 3},
        {"complaints_threshold": 5},
        {"recipient_emails": {"mio": ["mio@example.kz"], "gask": [], "law_enforcement": []}},
    ],
    ids=lambda change: next(iter(change)),
)
def test_other_settings_do_not_rescore(
    client: TestClient, db: Session, world: World, sent_tasks: list, change: dict[str, Any]
) -> None:
    make_object(db, world.ust)
    sent_tasks.clear()
    assert client.put(URL, headers=auth(world.users["admin"]), json=change).status_code == 200
    assert recalc_events(sent_tasks) == set()


def test_saving_the_same_value_does_not_rescore(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    make_object(db, world.ust)
    admin = auth(world.users["admin"])
    client.put(URL, headers=admin, json={"ad_window_days": 14})
    sent_tasks.clear()
    # The same value again, and a default that was never stored: nothing changes for the calculation.
    assert client.put(URL, headers=admin, json={"ad_window_days": 14, "zone_red_min": 60}).status_code == 200
    assert recalc_events(sent_tasks) == set()


def test_several_scoring_keys_queue_one_rescore_per_object(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    obj = make_object(db, world.ust)
    sent_tasks.clear()
    client.put(URL, headers=auth(world.users["admin"]), json={"ad_window_days": 14, "zone_yellow_min": 20})
    assert [args for name, args in sent_tasks if name == "risk.recalc_object"] == [(obj.id,)]


def test_a_rejected_change_rescores_nothing(client: TestClient, db: Session, world: World, sent_tasks: list) -> None:
    make_object(db, world.ust)
    sent_tasks.clear()
    response = client.put(
        URL, headers=auth(world.users["admin"]), json={"zone_yellow_min": 80}
    )  # above the red minimum
    assert response.status_code == 422
    assert recalc_events(sent_tasks) == set()


def test_only_the_global_admin_changes_settings(
    client: TestClient, db: Session, world: World, sent_tasks: list
) -> None:
    make_object(db, world.ust)
    sent_tasks.clear()
    assert client.put(URL, headers=auth(world.users["admin_semey"]), json={"ad_window_days": 14}).status_code == 403
    assert recalc_events(sent_tasks) == set()

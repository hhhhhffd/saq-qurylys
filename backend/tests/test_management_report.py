"""Management report PDF: figures for a period, scope isolation, validation, HTTP response."""

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdPost, AuditLog, Complaint, ConstructionObject, Developer, Inspection, RiskScore, SignalCard
from app.models.enums import AdStatus, KeyStatus, Platform, Recipient, ScoreTrigger, SignalOrigin, SignalStatus, Zone
from app.modules.dashboard import report
from app.modules.signals.pdf import _env, render_document
from tests.conftest import World, auth, make_object

TODAY = datetime.now(report.REPORT_TZ).date()
START = TODAY - timedelta(days=10)
URL = "/api/v1/dashboard/report.pdf"
PARAMS = {"from": START.isoformat(), "to": TODAY.isoformat()}


def at(day: date) -> datetime:
    return datetime.combine(day, time(12, 0), report.REPORT_TZ)


def score(db: Session, obj: ConstructionObject, zone: Zone, day: date) -> None:
    db.add(
        RiskScore(
            object_id=obj.id, score=70, zone=zone, breakdown={}, trigger=ScoreTrigger.event, calculated_at=at(day)
        )
    )


def page_texts(html: str) -> str:
    document = render_document(html)
    parts = [box.text for page in document.pages for box in page._page_box.descendants() if getattr(box, "text", None)]
    return re.sub(r"\s+", " ", " ".join(parts))


def render(
    db: Session,
    world: World,
    user: str,
    territory_id: int | None = None,
    zones: report.ReportZones = "priority",
) -> tuple[dict[str, Any], str]:
    from app.scope import build_scope

    account = world.users[user]
    context = report.build_context(
        db, account, build_scope(db, account), report.Period(START, TODAY), territory_id, datetime.now(UTC), zones
    )
    return context, page_texts(_env.get_template("management_report.html").render(**context))


def add_card(db: Session, obj: ConstructionObject, number: str, **fields: Any) -> SignalCard:
    card = SignalCard(number=number, object_id=obj.id, origin=SignalOrigin.manual, sections={}, **fields)
    db.add(card)
    db.flush()
    return card


def fill_world(db: Session, world: World) -> None:
    long_ago = at(START - timedelta(days=30))
    grew = make_object(db, world.ust, "ЖК Растущий", zone=Zone.red, score=70, created_at=long_ago)
    stable = make_object(db, world.ust, "ЖК Стабильный", zone=Zone.red, score=70, created_at=long_ago)
    make_object(db, world.ust, "ЖК Без оценки", created_at=long_ago)
    foreign = make_object(db, world.semey, "ЖК Семейский", zone=Zone.red, score=70, created_at=long_ago)
    score(db, grew, Zone.green, START - timedelta(days=5))
    score(db, grew, Zone.red, TODAY - timedelta(days=3))
    score(db, stable, Zone.red, START - timedelta(days=5))
    score(db, foreign, Zone.red, START - timedelta(days=5))

    inside, outside = at(TODAY - timedelta(days=2)), at(START - timedelta(days=3))
    add_card(db, grew, "SQ-T-1", created_at=inside, status=SignalStatus.requires_confirmation)
    add_card(db, grew, "SQ-T-2", created_at=outside, status=SignalStatus.requires_confirmation)
    add_card(
        db,
        stable,
        "SQ-T-3",
        created_at=outside,
        status=SignalStatus.sent,
        recipient=Recipient.gask,
        sent_at=inside,
        due_date=TODAY - timedelta(days=4),
    )
    add_card(
        db,
        stable,
        "SQ-T-4",
        created_at=outside,
        status=SignalStatus.responded,
        sent_at=outside,
        response_at=inside,
        due_date=TODAY - timedelta(days=4),
    )
    add_card(db, foreign, "SQ-T-5", created_at=inside, status=SignalStatus.sent, due_date=TODAY - timedelta(days=1))

    for obj, when, status, platform in (
        (grew, inside, AdStatus.captured, Platform.instagram),
        (grew, inside, AdStatus.removed_saved, Platform.telegram),
        (grew, inside, AdStatus.verification, Platform.instagram),
        (stable, outside, AdStatus.captured, Platform.instagram),
        (foreign, inside, AdStatus.captured, Platform.instagram),
    ):
        db.add(
            AdPost(
                platform=platform,
                object_id=obj.id,
                territory_id=obj.territory_id,
                published_at=when,
                captured_at=when,
                status=status,
            )
        )
    for obj, day, collective in (
        (grew, TODAY - timedelta(days=1), True),
        (grew, TODAY - timedelta(days=2), False),
        (stable, START - timedelta(days=1), False),
        (foreign, TODAY, False),
    ):
        db.add(Complaint(object_id=obj.id, received_at=day, is_collective=collective))
    db.add(Inspection(object_id=grew.id, inspected_at=TODAY, readiness_pct=40))
    db.add(Inspection(object_id=grew.id, inspected_at=START - timedelta(days=1), readiness_pct=30))
    db.add(Inspection(object_id=foreign.id, inspected_at=TODAY, readiness_pct=30))
    db.flush()


def test_empty_register_messages_distinguish_priority_from_all(db: Session, world: World) -> None:
    from app.scope import build_scope

    user = world.users["mio_ust"]
    scope = build_scope(db, user)
    period = report.Period(START, TODAY)
    priority = report.build_context(db, user, scope, period, None, datetime.now(UTC))
    all_objects = report.build_context(db, user, scope, period, None, datetime.now(UTC), zones="all")

    assert priority["register_rows"] == []
    assert priority["register"]["empty"] == "Красных и жёлтых объектов в доступной территории нет."
    assert all_objects["register_rows"] == []
    assert all_objects["register"]["empty"] == "В доступной территории объекты не найдены."


def test_figures_inside_period_only_and_scope_isolated(db: Session, world: World) -> None:
    fill_world(db, world)
    context, text = render(db, world, "mio_ust")

    by_code = {row["code"]: row for row in context["zones"]}
    assert (by_code["red"]["start"], by_code["red"]["end"], by_code["red"]["now"]) == (1, 2, 2)
    assert (by_code["green"]["start"], by_code["green"]["end"]) == (1, 0)
    assert by_code["red"]["change"] == "+1"
    assert by_code["none"]["end"] == 1
    assert [(row["name"], row["from"], row["to"]) for row in context["changes"]] == [
        ("ЖК Растущий", "Зелёная", "Красная")
    ]
    register_by_name = {row["name"]: row for row in context["register_rows"]}
    assert set(register_by_name) == {"ЖК Растущий", "ЖК Стабильный"}
    assert register_by_name["ЖК Растущий"]["zone"] == "Красная"
    assert register_by_name["ЖК Растущий"]["score"] == 70
    assert register_by_name["ЖК Растущий"]["assessment_date"] == "нет данных"
    assert context["register"]["mode"] == "Красные и жёлтые"
    assert "ЖК Без оценки" not in text
    assert dict(context["signals"]) == {
        "Создано за период": 1,
        "Направлено за период": 1,
        "Получено ответов за период": 1,
        "Просрочено сейчас": 1,
    }
    assert [(row["number"], row["days"], row["recipient"]) for row in context["overdue"]] == [("SQ-T-3", 4, "ГАСК")]
    assert (context["ads_total"], context["ads_removed"]) == (2, 1)
    assert context["ads_by_platform"] == [("Instagram", 1), ("Telegram", 1)]
    assert (context["complaints_total"], context["complaints_collective"]) == (2, 1)
    assert context["inspections_total"] == 1
    assert "Доклад о работе за период" in text
    assert "SQ-T-3" in text
    assert "ЖК Растущий" in text
    assert "SQ-T-5" not in text
    assert "ЖК Семейский" not in text
    assert context["territory"] == "Усть-Каменогорск"


def test_admin_sees_everything_and_can_narrow_to_a_territory(db: Session, world: World) -> None:
    fill_world(db, world)
    everything, _ = render(db, world, "admin")
    assert everything["territory"] == "вся Республика Казахстан"
    assert everything["complaints_total"] == 3
    assert everything["inspections_total"] == 2

    narrowed, _ = render(db, world, "admin", world.semey.id)
    assert narrowed["territory"] == "Семей"
    assert (narrowed["complaints_total"], narrowed["inspections_total"], narrowed["ads_total"]) == (1, 1, 1)
    assert [row["number"] for row in narrowed["overdue"]] == ["SQ-T-5"]
    narrowed_all, _ = render(db, world, "admin", world.semey.id, zones="all")
    assert [row["name"] for row in narrowed_all["register_rows"]] == ["ЖК Семейский"]
    assert all("Усть-Каменогорск" not in row["location"] for row in narrowed_all["register_rows"])

    region, _ = render(db, world, "mio_region", world.region.id)
    assert region["complaints_total"] == 3


def test_endpoint_returns_pdf_and_audits(client: TestClient, db: Session, world: World) -> None:
    fill_world(db, world)
    response = client.get(URL, params=PARAMS, headers=auth(world.users["mio_ust"]))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"] == f'inline; filename="doklad-{START}-{TODAY}.pdf"'
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "report.generate")).one()
    assert entry.after == {
        "from": START.isoformat(),
        "to": TODAY.isoformat(),
        "territory_id": None,
        "zones": "priority",
    }
    all_response = client.get(URL, params={**PARAMS, "zones": "all"}, headers=auth(world.users["mio_ust"]))
    assert all_response.status_code == 200
    entries = list(db.scalars(select(AuditLog).where(AuditLog.action == "report.generate").order_by(AuditLog.id)))
    assert [item.after["zones"] for item in entries] == ["priority", "all"]


def test_all_register_includes_green_unscored_identity_status_and_demo(db: Session, world: World) -> None:
    fill_world(db, world)
    developer = Developer(bin="123456789012", name="Застройщик Тест")
    db.add(developer)
    db.flush()
    make_object(
        db,
        world.ust,
        "ЖК Зелёный",
        code="REG-GREEN",
        address="ул. Центральная, 10",
        district_id=world.district.id,
        developer_id=developer.id,
        zone=Zone.green,
        score=20,
        last_scored_at=at(TODAY - timedelta(days=1)),
        key_status=KeyStatus.delayed,
        is_demo=True,
    )

    priority, _ = render(db, world, "mio_ust", zones="priority")
    all_context, text = render(db, world, "mio_ust", zones="all")

    assert {row["name"] for row in priority["register_rows"]} == {"ЖК Растущий", "ЖК Стабильный"}
    assert {row["name"] for row in all_context["register_rows"]} == {
        "ЖК Растущий",
        "ЖК Стабильный",
        "ЖК Без оценки",
        "ЖК Зелёный",
    }
    assert all_context["zones"] == priority["zones"]
    assert all_context["summary"] == priority["summary"]
    green = next(row for row in all_context["register_rows"] if row["code"] == "REG-GREEN")
    assert green["zone"] == "Зелёная"
    assert green["score"] == 20
    assert green["assessment_date"] == at(TODAY - timedelta(days=1)).astimezone(report.REPORT_TZ).strftime(
        "%d.%m.%Y %H:%M"
    )
    assert green["address"] == "ул. Центральная, 10"
    assert green["location"] == "Центральный · Усть-Каменогорск"
    assert green["developer"] == "Застройщик Тест"
    assert green["developer_bin"] == "123456789012"
    assert green["key_status"] == "Задержка строительства"
    unscored = next(row for row in all_context["register_rows"] if row["name"] == "ЖК Без оценки")
    assert unscored["score"] is None
    assert unscored["zone"] == "без оценки"
    assert unscored["assessment_date"] == "нет данных"
    assert "ул. Центральная, 10" in text
    assert "123456789012" in text
    assert "ДЕМО" not in text
    assert "Задержка строительства" in text
    assert "официальная передача материалов оформляется отдельной сигнальной карточкой" in text
    assert "Красная зона означает высокий риск" in text


def test_register_has_no_30_row_cap_and_is_deterministically_sorted(db: Session, world: World) -> None:
    objects = []
    for index in range(35):
        zone = Zone.yellow if index % 5 == 0 else Zone.red
        objects.append(
            make_object(
                db,
                world.ust,
                f"ЖК {index:02}",
                code=f"REG-{index:02}",
                zone=zone,
                score=70 + (index % 4),
            )
        )
    objects.append(make_object(db, world.ust, "ЖК Без балла", code="REG-NULL", zone=Zone.red))

    context, _ = render(db, world, "mio_ust")
    rows = context["register_rows"]
    expected = sorted(
        objects,
        key=lambda obj: (
            0 if obj.zone is Zone.red else 1,
            obj.score is None,
            -(obj.score or 0),
            obj.code,
            obj.name,
            obj.id,
        ),
    )

    matching_rows = [row for row in rows if row["code"].startswith("REG-")]
    assert len(matching_rows) == 36
    assert [row["code"] for row in matching_rows] == [obj.code for obj in expected]


def test_validation_and_access(client: TestClient, db: Session, world: World) -> None:
    headers = auth(world.users["mio_ust"])
    swapped = {"from": PARAMS["to"], "to": PARAMS["from"]}
    assert client.get(URL, params=swapped, headers=headers).status_code == 422
    too_long = {"from": (TODAY - timedelta(days=366)).isoformat(), "to": TODAY.isoformat()}
    assert client.get(URL, params=too_long, headers=headers).status_code == 422
    longest = {"from": (TODAY - timedelta(days=365)).isoformat(), "to": TODAY.isoformat()}
    assert client.get(URL, params=longest, headers=headers).status_code == 200
    assert client.get(URL, params={**PARAMS, "zones": "blue"}, headers=headers).status_code == 422
    assert client.get(URL, params={**PARAMS, "territory_id": world.semey.id}, headers=headers).status_code == 403
    assert client.get(URL, params={**PARAMS, "territory_id": world.ust.id}, headers=headers).status_code == 200
    for role in ("gask", "law"):
        assert client.get(URL, params=PARAMS, headers=auth(world.users[role])).status_code == 403
    assert client.get(URL, params=PARAMS).status_code == 401


def test_unknown_territory_is_404(client: TestClient, db: Session, world: World) -> None:
    response = client.get(URL, params={**PARAMS, "territory_id": 999_999}, headers=auth(world.users["admin"]))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "territory_not_found"

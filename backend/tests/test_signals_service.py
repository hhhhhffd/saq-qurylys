"""Signal card service: numbering, sections, deadlines and deadline notifications."""

from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.models import AppUser, Developer, Holiday, Notification, SignalCard, SignalCounter
from app.models.enums import (
    CheckSource,
    CheckStatus,
    DetectedBy,
    DocType,
    EvidenceKind,
    HolidayKind,
    NotificationKind,
    PhraseCategory,
    Recipient,
    ScoreTrigger,
    SignalOrigin,
    SignalStatus,
)
from app.modules.risk import service as risk
from app.modules.risk import tasks as risk_tasks
from app.modules.settings.service import save_settings
from app.modules.signals import service
from app.modules.signals import tasks as signal_tasks
from app.scope import build_scope
from app.storage import EvidenceLink
from app.worker.celery_app import celery_app
from tests.conftest import World, make_object
from tests.support_risk import NOW, add_ad, add_complaint, add_document

BOOKING = ((PhraseCategory.booking, DetectedBy.dictionary, None),)


def view_of(db: Session, user: AppUser, card: SignalCard) -> service.CardView:
    return service.get_card_view(db, user, build_scope(db, user), card.id)


def new_card(db: Session, world: World, now: datetime = NOW, **object_fields: object) -> SignalCard:
    obj = make_object(db, world.ust, "ЖК Алтын", **object_fields)
    return service.create_card(db, obj, SignalOrigin.manual, world.users["mio_ust"], now=now)


def send(
    db: Session, world: World, card: SignalCard, recipient: Recipient = Recipient.gask, now: datetime = NOW
) -> None:
    mio = world.users["mio_ust"]
    service.confirm_and_send(db, view_of(db, mio, card), mio, recipient, None, now)


# ---------------------------------------------------------------- numbering


def test_numbers_are_sequential_within_a_year(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    numbers = [
        service.create_card(db, obj, SignalOrigin.manual, world.users["mio_ust"], now=NOW).number for _ in range(3)
    ]
    assert numbers == ["SQ-2026-0001", "SQ-2026-0002", "SQ-2026-0003"]


def test_numbering_restarts_each_year(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    mio = world.users["mio_ust"]
    last_of_2026 = service.create_card(db, obj, SignalOrigin.manual, mio, now=datetime(2026, 12, 30, tzinfo=UTC))
    first_of_2027 = service.create_card(db, obj, SignalOrigin.manual, mio, now=datetime(2027, 1, 5, tzinfo=UTC))
    second_of_2027 = service.create_card(db, obj, SignalOrigin.manual, mio, now=datetime(2027, 1, 6, tzinfo=UTC))
    assert (last_of_2026.number, first_of_2027.number, second_of_2027.number) == (
        "SQ-2026-0001",
        "SQ-2027-0001",
        "SQ-2027-0002",
    )


def test_year_is_taken_in_the_territory_time_zone(db: Session, world: World) -> None:
    # 20:00 UTC on 31 Dec is already 1 Jan in Almaty.
    card = new_card(db, world, now=datetime(2026, 12, 31, 20, 0, tzinfo=UTC))
    assert card.number == "SQ-2027-0001"


def test_number_width_grows_past_9999(db: Session, world: World) -> None:
    db.add(SignalCounter(year=2026, last_number=9998))
    db.flush()
    obj = make_object(db, world.ust)
    mio = world.users["mio_ust"]
    numbers = [service.create_card(db, obj, SignalOrigin.manual, mio, now=NOW).number for _ in range(3)]
    assert numbers == ["SQ-2026-9999", "SQ-2026-10000", "SQ-2026-10001"]


# ---------------------------------------------------------------- due date


def test_due_date_counts_working_days_from_today(db: Session, world: World) -> None:
    card = new_card(db, world)  # created on Tuesday 13 Oct 2026 (Almaty)
    send(db, world, card)
    assert card.review_days == 5
    assert card.due_date == date(2026, 10, 20)
    assert card.sent_at == NOW


def test_due_date_skips_holidays_and_counts_transferred_workdays(db: Session, world: World) -> None:
    db.add(Holiday(day=date(2026, 10, 15), kind=HolidayKind.holiday, name="Праздник"))
    db.add(Holiday(day=date(2026, 10, 17), kind=HolidayKind.workday, name="Рабочая суббота"))
    db.flush()
    card = new_card(db, world)
    send(db, world, card)
    # Wed 14 (1), Thu 15 holiday, Fri 16 (2), Sat 17 transferred workday (3), Mon 19 (4), Tue 20 (5)
    assert card.due_date == date(2026, 10, 20)

    db.add(Holiday(day=date(2026, 10, 19), kind=HolidayKind.holiday, name="Ещё праздник"))
    db.flush()
    other = new_card(db, world)
    send(db, world, other)
    assert other.due_date == date(2026, 10, 21)


def test_due_date_uses_the_review_days_of_the_card(db: Session, world: World) -> None:
    save_settings(db, {"review_days": 2})
    card = new_card(db, world)
    assert card.review_days == 2
    send(db, world, card)
    assert card.due_date == date(2026, 10, 15)


def test_today_is_the_date_in_the_territory_time_zone(db: Session, world: World) -> None:
    thursday_evening_utc = datetime(2026, 10, 15, 20, 0, tzinfo=UTC)  # Friday 01:00 in Almaty
    card = new_card(db, world)
    card.review_days = 1
    send(db, world, card, now=thursday_evening_utc)
    assert card.due_date == date(2026, 10, 19)  # Friday + 1 working day, not Thursday + 1


# ---------------------------------------------------------------- sections


def test_sections_are_assembled_from_the_object_data(db: Session, world: World, bucket: str) -> None:
    developer = Developer(
        bin="123456789012", name="ТОО Застройщик", director="Иванов И.И.", founders=["Петров", "Сидоров"]
    )
    db.add(developer)
    db.flush()
    obj = make_object(
        db,
        world.ust,
        "ЖК Алтын",
        developer_id=developer.id,
        address="ул. Абая, 1",
        cadastral_number="05-123-456",
        land_purpose="Жилая застройка",
    )
    permit = add_document(db, obj, DocType.dsu_permit, CheckStatus.checking)
    permit.number, permit.check_source = "ДСУ-1", CheckSource.housing_portal
    scan = storage.put_evidence(
        db, b"%PDF-1.4 scan", EvidenceKind.document_scan, "application/pdf", link=EvidenceLink(document_id=permit.id)
    )
    recent = add_ad(db, obj, NOW - timedelta(days=1), hits=BOOKING, payment_schemes=("booking", "installment"))
    old = add_ad(db, obj, NOW - timedelta(days=9), hits=BOOKING)
    shot = storage.put_evidence(
        db, b"\x89PNG\r\n\x1a\nxx", EvidenceKind.screenshot_png, "image/png", link=EvidenceLink(ad_post_id=recent.id)
    )
    add_complaint(db, obj, collective=True, confirmed_payments=True, external_id="EO-77")
    risk.recalculate(db, obj.id, ScoreTrigger.event, NOW)

    card = service.create_card(db, obj, SignalOrigin.manual, world.users["mio_ust"], now=NOW)
    sections = card.sections

    assert sections["object_developer"] == {
        "object_code": obj.code,
        "object_name": "ЖК Алтын",
        "address": "ул. Абая, 1",
        "cadastral_number": "05-123-456",
        "land_purpose": "Жилая застройка",
        "developer_name": "ТОО Застройщик",
        "bin": "123456789012",
        "director": "Иванов И.И.",
        "founders": ["Петров", "Сидоров"],
    }
    assert sections["permit_checks"] == [
        {
            "doc_type": "dsu_permit",
            "source": "housing_portal",
            "check_status": "checking",
            "checked_at": None,
            "number": "ДСУ-1",
            "evidence_ids": [scan.id],
        }
    ]
    assert [item["ad_post_id"] for item in sections["publications"]] == [recent.id]  # the 9-day-old ad is outside
    assert sections["publications"][0]["evidence_ids"] == [shot.id]
    assert sections["publications"][0]["platform"] == "instagram"
    assert old.id not in {item["ad_post_id"] for item in sections["publications"]}
    assert {item["code"] for item in sections["risk_factors"]} == {
        "no_permit",
        "money_offer",
        "active_ads",
        "complaints",
    }
    assert all(set(item) == {"code", "weight", "detail"} for item in sections["risk_factors"])
    assert sections["scheme_payments"]["payment_schemes"] == ["booking", "installment"]
    assert sections["scheme_payments"]["contract_types"] == []
    assert "EO-77" in sections["scheme_payments"]["confirmed_payments_note"]
    assert sections["proposed_measures"] == ["request_documents", "interview_complainants", "request_payments_info"]
    assert sections["route"] == {"recipient": None, "review_days": 5}
    assert sections["note"] == ""


def test_sections_of_a_bare_object_are_empty_but_complete(db: Session, world: World) -> None:
    sections = new_card(db, world).sections
    assert set(sections) == {
        "object_developer",
        "risk_factors",
        "permit_checks",
        "publications",
        "scheme_payments",
        "proposed_measures",
        "route",
        "note",
    }
    assert sections["risk_factors"] == [] and sections["permit_checks"] == [] and sections["publications"] == []
    assert sections["object_developer"]["developer_name"] is None
    assert sections["scheme_payments"] == {"payment_schemes": [], "contract_types": [], "confirmed_payments_note": ""}


def test_covert_contract_categories_become_contract_types(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    add_ad(db, obj, hits=((PhraseCategory.covert_contract, DetectedBy.dictionary, None),))
    risk.recalculate(db, obj.id, ScoreTrigger.event, NOW)
    card = service.create_card(db, obj, SignalOrigin.auto, None, now=NOW)
    assert card.sections["scheme_payments"]["contract_types"] == [service.CONTRACT_TYPE_LABELS["covert_contract"]]


def test_publications_are_capped_and_most_incriminating_first(db: Session, world: World) -> None:
    obj = make_object(db, world.ust)
    ads = [add_ad(db, obj, NOW - timedelta(minutes=index)) for index in range(service.MAX_PUBLICATIONS + 5)]
    heaviest = ads[40]
    heaviest.max_phrase_weight = 99
    db.flush()
    card = service.create_card(db, obj, SignalOrigin.manual, world.users["mio_ust"], now=NOW)
    publications = card.sections["publications"]
    assert len(publications) == service.MAX_PUBLICATIONS
    assert publications[0]["ad_post_id"] == heaviest.id
    assert publications[1]["ad_post_id"] == ads[0].id  # then the newest


# ---------------------------------------------------------------- deadline notifications


def _kinds(db: Session, card: SignalCard, kind: NotificationKind) -> set[int]:
    return set(
        db.scalars(
            select(Notification.user_id).where(
                Notification.kind == kind, Notification.entity_type == "signal_card", Notification.entity_id == card.id
            )
        )
    )


def test_due_soon_fires_one_working_day_before_and_only_once(db: Session, world: World) -> None:
    card = new_card(db, world)
    send(db, world, card)  # due Tuesday 2026-10-20
    expected = {world.users["mio_ust"].id, world.users["mio_region"].id, world.users["gask"].id}

    assert service.check_deadlines(db, datetime(2026, 10, 18, 6, tzinfo=UTC)) == 0  # Sunday: two days away
    assert service.check_deadlines(db, datetime(2026, 10, 19, 1, tzinfo=UTC)) == 3  # Monday, one working day before
    assert _kinds(db, card, NotificationKind.signal_due_soon) == expected
    assert service.check_deadlines(db, datetime(2026, 10, 19, 6, tzinfo=UTC)) == 0  # same day again
    assert service.check_deadlines(db, datetime(2026, 10, 20, 1, tzinfo=UTC)) == 0  # on the due date: already told


def test_due_soon_accounts_for_weekends_and_holidays(db: Session, world: World) -> None:
    save_settings(db, {"review_days": 1})
    card = new_card(db, world, now=datetime(2026, 10, 15, 2, tzinfo=UTC))  # Thursday
    send(db, world, card, now=datetime(2026, 10, 15, 2, tzinfo=UTC))
    assert card.due_date == date(2026, 10, 16)  # Friday
    db.add(Holiday(day=date(2026, 10, 15), kind=HolidayKind.holiday, name="x"))  # Thursday becomes a day off
    db.flush()
    # the working day before Friday is now Wednesday
    assert service.check_deadlines(db, datetime(2026, 10, 14, 2, tzinfo=UTC)) == 3


def test_overdue_fires_the_day_after_the_deadline_and_only_once(db: Session, world: World) -> None:
    card = new_card(db, world)
    send(db, world, card)  # due 2026-10-20
    assert service.check_deadlines(db, datetime(2026, 10, 21, 1, tzinfo=UTC)) == 3
    assert _kinds(db, card, NotificationKind.signal_overdue) == {
        world.users["mio_ust"].id,
        world.users["mio_region"].id,
        world.users["gask"].id,
    }
    assert _kinds(db, card, NotificationKind.signal_due_soon) == set()  # the warning window was missed entirely
    assert service.check_deadlines(db, datetime(2026, 10, 21, 5, tzinfo=UTC)) == 0
    assert service.check_deadlines(db, datetime(2026, 10, 25, 1, tzinfo=UTC)) == 0


def test_notifications_follow_territory_and_recipient(db: Session, world: World) -> None:
    card = new_card(db, world)
    send(db, world, card, recipient=Recipient.law_enforcement)
    service.check_deadlines(db, datetime(2026, 10, 21, 1, tzinfo=UTC))
    recipients = _kinds(db, card, NotificationKind.signal_overdue)
    # law_enforcement works on the region (covers Ust-Kamenogorsk); gask is not the addressee; Semey is another city
    assert recipients == {world.users["mio_ust"].id, world.users["mio_region"].id, world.users["law"].id}


def test_a_card_addressed_to_the_mio_warns_the_officers_of_the_territory(db: Session, world: World) -> None:
    card = new_card(db, world)
    send(db, world, card, recipient=Recipient.mio)
    assert service.check_deadlines(db, datetime(2026, 10, 21, 1, tzinfo=UTC)) == 2
    assert _kinds(db, card, NotificationKind.signal_overdue) == {
        world.users["mio_ust"].id,
        world.users["mio_region"].id,
    }


@pytest.mark.parametrize(
    "status", [SignalStatus.requires_confirmation, SignalStatus.returned, SignalStatus.responded, SignalStatus.closed]
)
def test_only_cards_waiting_for_an_answer_are_tracked(db: Session, world: World, status: SignalStatus) -> None:
    card = new_card(db, world)
    send(db, world, card)
    card.status = status
    db.flush()
    assert service.check_deadlines(db, datetime(2026, 10, 25, 1, tzinfo=UTC)) == 0


def test_a_late_run_still_catches_up_once(db: Session, world: World) -> None:
    card = new_card(db, world)
    send(db, world, card)
    # The job did not run on the working day before the deadline; running on the due date itself still warns.
    assert service.check_deadlines(db, datetime(2026, 10, 20, 1, tzinfo=UTC)) == 3
    assert len(_kinds(db, card, NotificationKind.signal_due_soon)) == 3
    assert service.check_deadlines(db, datetime(2026, 10, 20, 7, tzinfo=UTC)) == 0


def test_deadline_task_commits_through_its_own_session(
    db: Session, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(signal_tasks, "get_sessionmaker", lambda: lambda: nullcontext(db))
    monkeypatch.setattr(
        signal_tasks,
        "check_deadlines",
        lambda session: service.check_deadlines(session, datetime(2026, 10, 21, 1, tzinfo=UTC)),
    )
    card = new_card(db, world)
    send(db, world, card)
    assert signal_tasks.check_deadlines_task() == 3
    assert signal_tasks.check_deadlines_task() == 0


def test_celery_task_names_are_the_contract() -> None:
    assert risk_tasks.recalc_object.name == "risk.recalc_object"
    assert risk_tasks.sweep_due.name == "risk.sweep_due"
    assert risk_tasks.red_zone.name == "notify.red_zone"
    assert signal_tasks.check_deadlines_task.name == "signals.check_deadlines"
    for name in ("risk.recalc_object", "risk.sweep_due", "notify.red_zone", "signals.check_deadlines"):
        assert name in celery_app.conf.task_routes

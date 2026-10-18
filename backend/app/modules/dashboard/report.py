"""One-button PDF report for heads of departments: figures for a period over the user's territory."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import Date, Select, case, func, select
from sqlalchemy.orm import Session

from app.models import (
    AdPost,
    AppUser,
    Complaint,
    ConstructionObject,
    Developer,
    District,
    Inspection,
    SignalCard,
    Territory,
)
from app.models.enums import AdStatus, SignalStatus, Zone
from app.modules.dashboard.service import build_timeline
from app.modules.risk.queries import AD_TIMESTAMP
from app.modules.signals.labels import get_labels
from app.modules.signals.pdf import _env, render_document
from app.modules.signals.service import card_stmt, local_today
from app.scope import TerritoryScope

MAX_PERIOD_DAYS = 366
MAX_LISTED = 30
ReportZones = Literal["priority", "all"]
# The country lives in one reporting time zone; a period is whole local days.
REPORT_TZ = ZoneInfo("Asia/Almaty")
ZONE_ORDER: tuple[Zone | None, ...] = (Zone.red, Zone.yellow, Zone.green, None)
REGISTER_LABELS = {
    "title": "Перечень ЖК на дату формирования",
    "priority": "Красные и жёлтые",
    "all": "Все объекты",
    "empty_priority": "Красных и жёлтых объектов в доступной территории нет.",
    "empty_all": "В доступной территории объекты не найдены.",
    "object": "ЖК / адрес",
    "developer": "Застройщик / БИН",
    "risk": "Зона / балл",
    "assessment": "Последняя оценка / статус",
    "no_score": "Без оценки",
    "demo": "ДЕМО",
}


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @property
    def start_at(self) -> datetime:
        return datetime.combine(self.start, time.min, REPORT_TZ)

    @property
    def end_at(self) -> datetime:
        """Exclusive end: the first moment after the last day of the period."""
        return datetime.combine(self.end + timedelta(days=1), time.min, REPORT_TZ)


def narrow_scope(session: Session, scope: TerritoryScope, territory_id: int) -> TerritoryScope:
    """The part of the user's scope inside the subtree of one territory (a region includes its cities)."""
    subtree = select(Territory.id).where(Territory.id == territory_id).cte("subtree", recursive=True)
    subtree = subtree.union_all(select(Territory.id).join(subtree, Territory.parent_id == subtree.c.id))
    ids = frozenset(session.scalars(select(subtree.c.id)))
    return TerritoryScope(ids=ids if scope.ids is None else ids & scope.ids)


def _in_period(column: Any, period: Period) -> Any:
    return (column >= period.start_at) & (column < period.end_at)


def _count(session: Session, stmt: Select[Any]) -> int:
    return session.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def _format_assessment_date(value: datetime | None, missing: str) -> str:
    if value is None:
        return missing
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(REPORT_TZ).strftime("%d.%m.%Y %H:%M")


def _zones_at(session: Session, scope: TerritoryScope, at: datetime) -> dict[int, Zone]:
    return {item.object_id: item.zone for item in build_timeline(session, scope, [at]).frames[0].objects}


def _zone_counts(session: Session, scope: TerritoryScope, at: datetime) -> dict[Zone | None, int]:
    """Objects by zone at a moment: the latest score of each; objects already existing but unscored are `None`."""
    zones = _zones_at(session, scope, at)
    counts: dict[Zone | None, int] = dict.fromkeys(ZONE_ORDER, 0)
    for zone in zones.values():
        counts[zone] += 1
    existing = _count(
        session,
        scope.restrict(
            select(ConstructionObject.id).where(ConstructionObject.created_at <= at), ConstructionObject.territory_id
        ),
    )
    counts[None] = max(existing - len(zones), 0)
    return counts


def _zone_changes(
    session: Session, scope: TerritoryScope, start: datetime, end: datetime
) -> list[tuple[Any, Zone | None, Zone | None]]:
    """Scored objects whose zone at `end` differs from the one at `start`, the most dangerous now first."""
    before, after = _zones_at(session, scope, start), _zones_at(session, scope, end)
    # An object scored for the first time in the period did not change its zone: it had none.
    changed = {oid: (zone, after[oid]) for oid, zone in before.items() if oid in after and zone != after[oid]}
    objects = session.execute(
        select(ConstructionObject.id, ConstructionObject.name, ConstructionObject.code).where(
            ConstructionObject.id.in_(changed)
        )
    ).all()
    rows: list[tuple[Any, Zone | None, Zone | None]] = [(obj, *changed[obj.id]) for obj in objects]
    rows.sort(key=lambda row: (ZONE_ORDER.index(row[2]), row[0].name, row[0].id))
    return rows


def build_context(
    session: Session,
    user: AppUser,
    scope: TerritoryScope,
    period: Period,
    territory_id: int | None,
    now: datetime,
    zones: ReportZones = "priority",
) -> dict[str, Any]:
    labels = get_labels(user.locale.value)
    t = labels["management_report"]
    zone_names = {**labels["zone"], None: t["zone_none"]}
    territory_name = t["whole_country"]
    named_territory_id = territory_id or user.territory_id
    if named_territory_id is not None:
        territory_name = session.scalars(select(Territory.name).where(Territory.id == named_territory_id)).one()
    if territory_id is not None:
        scope = narrow_scope(session, scope, territory_id)

    # The end moment is capped at "now": a period reaching into today shows the real state.
    end_moment = min(period.end_at, now)
    at_start = _zone_counts(session, scope, period.start_at)
    at_end = _zone_counts(session, scope, end_moment)

    # Read the current projection once so the register and the "now" counters share a snapshot.
    current_stmt = (
        select(ConstructionObject, Developer.name, Developer.bin, District.name, Territory.name)
        .outerjoin(Developer, Developer.id == ConstructionObject.developer_id)
        .outerjoin(District, District.id == ConstructionObject.district_id)
        .join(Territory, Territory.id == ConstructionObject.territory_id)
    )
    current_stmt = scope.restrict(current_stmt, ConstructionObject.territory_id)
    zone_order = case(
        (ConstructionObject.zone == Zone.red, 0),
        (ConstructionObject.zone == Zone.yellow, 1),
        (ConstructionObject.zone == Zone.green, 2),
        else_=3,
    )
    current_rows = session.execute(
        current_stmt.order_by(
            zone_order,
            ConstructionObject.score.desc().nulls_last(),
            ConstructionObject.code,
            ConstructionObject.name,
            ConstructionObject.id,
        )
    ).all()
    current: dict[Zone | None, int] = dict.fromkeys(ZONE_ORDER, 0)
    register_rows = []
    for obj, developer_name, developer_bin, district_name, object_territory_name in current_rows:
        current[obj.zone] += 1
        if zones == "priority" and obj.zone not in (Zone.red, Zone.yellow):
            continue
        location = " · ".join(value for value in (district_name, object_territory_name) if value)
        register_rows.append(
            {
                "name": obj.name,
                "code": obj.code,
                "address": obj.address or labels["empty"],
                "location": location or labels["empty"],
                "developer": developer_name or labels["empty"],
                "developer_bin": developer_bin,
                "score": obj.score,
                "zone": zone_names[obj.zone.value if obj.zone else None],
                "zone_code": obj.zone.value if obj.zone else "none",
                "assessment_date": _format_assessment_date(obj.last_scored_at, labels["empty"]),
                "key_status": (
                    labels["dossier"]["key_status"].get(obj.key_status.value, obj.key_status.value)
                    if obj.key_status
                    else labels["empty"]
                ),
                "is_demo": obj.is_demo,
            }
        )

    def zone_key(zone: Zone | None) -> str:
        return zone.value if zone else "none"

    zones_table = [
        {
            "label": zone_names[zone.value if zone else None],
            "code": zone_key(zone),
            "start": at_start[zone],
            "end": at_end[zone],
            "now": current[zone],
            "change": f"{at_end[zone] - at_start[zone]:+d}" if at_end[zone] != at_start[zone] else "0",
        }
        for zone in ZONE_ORDER
    ]

    changes = _zone_changes(session, scope, period.start_at, end_moment)
    changes_rows = [
        {
            "name": obj.name,
            "code": obj.code,
            "from": zone_names[a.value if a else None],
            "from_code": zone_key(a),
            "to": zone_names[b.value if b else None],
            "to_code": zone_key(b),
        }
        for obj, a, b in changes[:MAX_LISTED]
    ]

    cards = card_stmt(user, scope)
    created, sent, responded = session.execute(
        cards.with_only_columns(
            func.count().filter(_in_period(SignalCard.created_at, period)),
            func.count().filter(_in_period(SignalCard.sent_at, period)),
            func.count().filter(_in_period(SignalCard.response_at, period)),
        ).order_by(None)
    ).one()
    # Overdue is judged by the local date of the object's territory.
    overdue_cards = cards.where(
        SignalCard.status == SignalStatus.sent,
        SignalCard.due_date < func.timezone(Territory.timezone, now).cast(Date),
    )
    overdue_total = session.scalar(overdue_cards.with_only_columns(func.count()).order_by(None)) or 0
    overdue = session.execute(overdue_cards.order_by(SignalCard.due_date, SignalCard.number).limit(MAX_LISTED)).all()
    overdue_rows = [
        {
            "number": card.number,
            "object": object_name,
            "recipient": labels["recipient"].get(card.recipient.value, card.recipient.value) if card.recipient else "",
            "due_date": card.due_date.strftime("%d.%m.%Y"),
            "days": (local_today(timezone, now) - card.due_date).days,
        }
        for card, object_name, _, timezone, _ in overdue
        if card.due_date is not None  # always true: the query selects cards with a due date
    ]

    ads = session.execute(
        scope.restrict(
            select(AdPost.platform, AdPost.status).where(
                _in_period(AD_TIMESTAMP, period),
                # A link nobody confirmed is not counted (as in the dossier and the signal card sections).
                AdPost.status != AdStatus.verification,
            ),
            AdPost.territory_id,
        )
    ).all()
    by_platform: dict[str, int] = {}
    for platform, _ in ads:
        name = labels["platform"].get(platform.value, platform.value)
        by_platform[name] = by_platform.get(name, 0) + 1

    # Complaints and inspections have no territory of their own: it is the object's.
    complaints = session.execute(
        scope.restrict(
            select(Complaint.is_collective)
            .join(ConstructionObject, ConstructionObject.id == Complaint.object_id)
            .where(Complaint.received_at.between(period.start, period.end)),
            ConstructionObject.territory_id,
        )
    ).all()
    inspections = _count(
        session,
        scope.restrict(
            select(Inspection.id)
            .join(ConstructionObject, ConstructionObject.id == Inspection.object_id)
            .where(Inspection.inspected_at.between(period.start, period.end)),
            ConstructionObject.territory_id,
        ),
    )

    s = t["summary"]
    red_start, red_now = at_start[Zone.red], current[Zone.red]
    summary = [
        s["objects"].format(total=sum(at_end.values())),
        (s["red"] if red_start != red_now else s["red_same"]).format(red=red_now, red_start=red_start),
        s["changed"].format(changed=len(changes)),
        s["signals"].format(created=created, sent=sent, responded=responded),
        s["overdue"].format(overdue=overdue_total) if overdue_total else s["no_overdue"],
        s["ads"].format(ads=len(ads), complaints=len(complaints), inspections=inspections),
    ]
    return {
        "t": t,
        "lang": labels["lang"],
        "product": labels["product"],
        "page": labels["page"],
        "page_of": labels["page_of"],
        "period": f"{period.start:%d.%m.%Y} — {period.end:%d.%m.%Y}",
        "territory": territory_name,
        "formed_by": user.full_name,
        "formed_on": now.astimezone(REPORT_TZ).strftime("%d.%m.%Y"),
        "summary": summary,
        "zones": zones_table,
        "register": {
            **REGISTER_LABELS,
            "mode": REGISTER_LABELS[zones],
            "empty": REGISTER_LABELS["empty_priority" if zones == "priority" else "empty_all"],
            "as_of": now.astimezone(REPORT_TZ).strftime("%d.%m.%Y %H:%M"),
        },
        "register_rows": register_rows,
        "changes": changes_rows,
        "changes_total": len(changes),
        "signals": [
            (t["signals_table"]["created"], created),
            (t["signals_table"]["sent"], sent),
            (t["signals_table"]["responded"], responded),
            (t["signals_table"]["overdue"], overdue_total),
        ],
        "overdue": overdue_rows,
        "overdue_total": overdue_total,
        "ads_total": len(ads),
        "ads_removed": sum(status is AdStatus.removed_saved for _, status in ads),
        "ads_by_platform": sorted(by_platform.items(), key=lambda item: (-item[1], item[0])),
        "complaints_total": len(complaints),
        "complaints_collective": sum(is_collective for (is_collective,) in complaints),
        "inspections_total": inspections,
        "note": (
            t["note"] + " Балл и зона помогают определить приоритет проверки; официальная передача материалов "
            "оформляется отдельной сигнальной карточкой."
        ),
    }


def render_pdf(
    session: Session,
    user: AppUser,
    scope: TerritoryScope,
    period: Period,
    territory_id: int | None,
    zones: ReportZones = "priority",
) -> bytes:
    context = build_context(session, user, scope, period, territory_id, datetime.now(UTC), zones)
    html = _env.get_template("management_report.html").render(**context)
    return bytes(render_document(html).write_pdf())

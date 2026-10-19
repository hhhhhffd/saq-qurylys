"""Signal card lifecycle (SPEC section 7): creation, editing, transitions and deadline notifications.

Functions flush and write the audit trail but never commit; the caller owns the transaction.
Sending to an external body happens only in `confirm_and_send`, which the router exposes to the
`mio_officer` role alone.
"""

import copy
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import audit
from app.calendar import add_working_days, load_overrides, shift_working_days
from app.errors import api_error, forbidden
from app.models import (
    AdPost,
    AppUser,
    AuditLog,
    Complaint,
    ConstructionObject,
    Developer,
    Document,
    Evidence,
    Notification,
    PhraseHit,
    SignalCard,
    SignalCounter,
    Territory,
)
from app.models.enums import (
    AdStatus,
    ConstructionStatus,
    EvidenceKind,
    NotificationKind,
    Recipient,
    Role,
    SignalOrigin,
    SignalStatus,
    Zone,
)
from app.modules.risk.engine import HIT_REJECTED, R1, R2, R4, R5, R6, HitFact, hit_kind
from app.modules.risk.queries import AD_TIMESTAMP, latest_score_stmt
from app.modules.settings.service import load_settings
from app.modules.signals.notifications import add_notifications, users_covering_territory
from app.modules.signals.schemas import ProposedMeasure, SignalAuditEntry, SignalDetail, SignalPatch, SignalRow
from app.scope import TerritoryScope

logger = logging.getLogger(__name__)

RECIPIENT_ROLE = {
    Recipient.mio: Role.mio_officer,
    Recipient.gask: Role.gask,
    Recipient.law_enforcement: Role.law_enforcement,
}
# Receiving bodies see only cards addressed to their own role.
ROLE_RECIPIENT = {Role.gask: Recipient.gask, Role.law_enforcement: Recipient.law_enforcement}

OPEN_STATUSES = (SignalStatus.requires_confirmation, SignalStatus.returned, SignalStatus.sent)
EDITABLE_STATUSES = (SignalStatus.requires_confirmation, SignalStatus.returned)
DELIVERED_STATUSES = (SignalStatus.sent, SignalStatus.responded, SignalStatus.closed)

MAX_PUBLICATIONS = 50
CONTRACT_TYPE_LABELS = {
    "preliminary_contract": "Предварительный договор",
    "covert_contract": "Договор в скрытой форме (инвестирование, резервирование)",
}


@dataclass(frozen=True)
class CardView:
    card: SignalCard
    object_name: str
    zone: Zone | None
    timezone: str
    is_demo: bool


def invalid_status() -> Exception:
    return api_error(409, "signal_invalid_status", "Действие недоступно для карточки в текущем статусе")


def local_today(timezone: str, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone)).date()


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value else None


# ---------------------------------------------------------------- numbering and sections


def allocate_number(session: Session, year: int) -> str:
    """SQ-YYYY-NNNN from the per-year counter. The upsert locks the counter row until the transaction
    ends, so concurrent cards get distinct numbers; the width grows past 9999."""
    stmt = (
        insert(SignalCounter)
        .values(year=year, last_number=1)
        .on_conflict_do_update(index_elements=[SignalCounter.year], set_={"last_number": SignalCounter.last_number + 1})
        .returning(SignalCounter.last_number)
    )
    return f"SQ-{year}-{session.execute(stmt).scalar_one():04d}"


def _payments_note(complaints: list[Complaint]) -> str:
    if not complaints:
        return ""
    refs = "; ".join(f"№ {item.external_id or item.id} от {item.received_at:%d.%m.%Y}" for item in complaints)
    return f"Заявители подтвердили внесение платежей застройщику. Обращения: {refs}."


def breakdown_parts(breakdown: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """(factors, needs_check, legal_basis_status) of a stored breakdown. A score from before the case model
    is a plain list of old factors: it says nothing about the current rules, so it is read as empty."""
    if not isinstance(breakdown, dict):
        return [], [], None
    return breakdown["factors"], breakdown["needs_check"], breakdown["legal_basis_status"]


def _hit_entries(session: Session, ad_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Phrase hits of publications as facts or AI hypotheses; rejected ones are left out."""
    entries: dict[int, list[dict[str, Any]]] = {ad_id: [] for ad_id in ad_ids}
    for hit in session.scalars(
        select(PhraseHit)
        .where(PhraseHit.ad_post_id.in_(ad_ids))
        .order_by(PhraseHit.ad_post_id, PhraseHit.start, PhraseHit.id)
    ):
        kind = hit_kind(HitFact(category=hit.category, detected_by=hit.detected_by, confirmed=hit.confirmed, id=hit.id))
        if kind != HIT_REJECTED:
            entries[hit.ad_post_id].append(
                {
                    "id": hit.id,
                    "category": hit.category.value,
                    "fragment": hit.matched_text,
                    "detected_by": hit.detected_by.value,
                    "confirmed": hit.confirmed,
                    "kind": kind,
                }
            )
    return entries


def build_sections(session: Session, obj: ConstructionObject, review_days: int, now: datetime) -> dict[str, Any]:
    """Sections of SPEC 7.1 from the current object data, its latest score, documents and recent publications.

    Besides the contract sections the card carries the legal basis status and the "needs check" flags, and each
    publication lists its phrase hits as a fact or an AI hypothesis."""
    window_days = load_settings(session).ad_window_days
    developer = session.get(Developer, obj.developer_id) if obj.developer_id else None
    latest = session.scalar(latest_score_stmt(obj.id))
    breakdown, needs_check, basis_status = breakdown_parts(latest.breakdown if latest else None)
    factors = {item["code"]: item for item in breakdown}
    triggered = {code for code, item in factors.items() if item["triggered"]}

    documents = session.scalars(select(Document).where(Document.object_id == obj.id).order_by(Document.id)).all()
    ads = session.scalars(
        select(AdPost)
        .where(
            AdPost.object_id == obj.id,
            AdPost.status != AdStatus.verification,  # a link nobody confirmed is not evidence about this object
            now - timedelta(days=window_days) <= AD_TIMESTAMP,
        )
        .order_by(AdPost.max_phrase_weight.desc(), AD_TIMESTAMP.desc(), AdPost.id.desc())
        .limit(MAX_PUBLICATIONS)
    ).all()
    ad_evidence: dict[int, list[int]] = {ad.id: [] for ad in ads}
    for evidence_id, ad_id in session.execute(
        select(Evidence.id, Evidence.ad_post_id).where(Evidence.ad_post_id.in_(ad_evidence)).order_by(Evidence.id)
    ):
        if ad_id is not None:
            ad_evidence[ad_id].append(evidence_id)
    ad_hits = _hit_entries(session, list(ad_evidence))
    paid_complaints = list(
        session.scalars(
            select(Complaint)
            .where(Complaint.object_id == obj.id, Complaint.confirmed_payments.is_(True))
            .order_by(Complaint.received_at, Complaint.id)
        )
    )

    money = factors.get(R2, {}).get("detail", {})
    measures = [
        measure
        for measure, needed in (
            (ProposedMeasure.request_documents, R1 in triggered or basis_status == "unknown"),
            (
                ProposedMeasure.site_inspection,
                R5 in triggered or R6 in triggered or obj.construction_status is ConstructionStatus.stalled,
            ),
            (ProposedMeasure.interview_complainants, R4 in triggered),
            (ProposedMeasure.request_payments_info, R2 in triggered or bool(paid_complaints)),
        )
        if needed
    ]
    return {
        "object_developer": {
            "object_code": obj.code,
            "object_name": obj.name,
            "address": obj.address,
            "cadastral_number": obj.cadastral_number,
            "land_purpose": obj.land_purpose,
            "developer_name": developer.name if developer else None,
            "bin": developer.bin if developer else None,
            "director": developer.director if developer else None,
            "founders": list(developer.founders) if developer else [],
        },
        "is_demo": obj.is_demo,
        "legal_basis_status": basis_status,
        "needs_check": needs_check,
        "risk_factors": [
            {
                "code": item["code"],
                "label": item["label"],
                "weight": item["weight"],
                "detail": item["detail"],
                "evidence": item["evidence"],
            }
            for item in breakdown
            if item["triggered"]
        ],
        "permit_checks": [
            {
                "doc_type": doc.doc_type.value,
                "source": doc.check_source.value if doc.check_source else None,
                "check_status": doc.check_status.value,
                "checked_at": _iso(doc.checked_at),
                "number": doc.number,
                "evidence_ids": [item.id for item in doc.evidence],
            }
            for doc in documents
        ],
        "publications": [
            {
                "ad_post_id": ad.id,
                "platform": ad.platform.value,
                "url": ad.url,
                "published_at": _iso(ad.published_at),
                "captured_at": _iso(ad.captured_at),
                "evidence_ids": ad_evidence[ad.id],
                "status": ad.status.value,
                "is_demo": ad.is_demo,
                "hits": ad_hits[ad.id],
            }
            for ad in ads
        ],
        "scheme_payments": {
            "payment_schemes": list(money.get("payment_schemes", [])),
            "contract_types": [
                CONTRACT_TYPE_LABELS[category]
                for category in money.get("categories", [])
                if category in CONTRACT_TYPE_LABELS
            ],
            "confirmed_payments_note": _payments_note(paid_complaints),
        },
        "proposed_measures": [measure.value for measure in measures],
        "route": {"recipient": None, "review_days": review_days},
        "note": "",
    }


# ---------------------------------------------------------------- creation and editing


def lock_object(session: Session, object_id: int) -> ConstructionObject | None:
    """Take the object row lock that serialises everything deciding about the object's open card: score
    recalculations (which draft a card on entering red) and the manual creation of a card. `FOR NO KEY UPDATE`
    is enough for that and, unlike `FOR UPDATE`, does not block other transactions adding documents or
    complaints (they take FOR KEY SHARE)."""
    return session.scalar(
        select(ConstructionObject)
        .where(ConstructionObject.id == object_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )


def open_card(session: Session, object_id: int) -> SignalCard | None:
    """A card that is being prepared or waits for the receiving body; the auto-draft rule keys on this."""
    return session.scalar(
        select(SignalCard)
        .where(SignalCard.object_id == object_id, SignalCard.status.in_(OPEN_STATUSES))
        .order_by(SignalCard.id)
        .limit(1)
    )


def has_open_card(session: Session, object_id: int) -> bool:
    return open_card(session, object_id) is not None


def create_manual_card(session: Session, obj: ConstructionObject, user: AppUser, request: Request | None) -> SignalCard:
    """A card made by an officer. At most one card per object is open at a time: with the object locked, the
    check cannot race a recalculation that drafts a card for an object that has just turned red."""
    lock_object(session, obj.id)
    existing = open_card(session, obj.id)
    if existing is not None:
        raise api_error(
            409,
            "signal_open_exists",
            f"У объекта уже есть открытая сигнальная карточка {existing.number}: продолжите работу с ней",
        )
    return create_card(session, obj, SignalOrigin.manual, user, request)


def create_card(
    session: Session,
    obj: ConstructionObject,
    origin: SignalOrigin,
    user: AppUser | None,
    request: Request | None = None,
    now: datetime | None = None,
) -> SignalCard:
    now = now or datetime.now(UTC)
    territory = session.get(Territory, obj.territory_id)
    if territory is None:
        raise ValueError(f"object {obj.id} has no territory")
    review_days = load_settings(session).review_days
    card = SignalCard(
        number=allocate_number(session, local_today(territory.timezone, now).year),
        object_id=obj.id,
        origin=origin,
        sections=build_sections(session, obj, review_days, now),
        review_days=review_days,
        created_by=user.id if user else None,
    )
    session.add(card)
    session.flush()
    session.refresh(card)
    audit.record(session, user, "signal_card.create", "signal_card", card.id, None, audit.snapshot(card), request)
    return card


def update_card(
    session: Session, card: SignalCard, patch: SignalPatch, user: AppUser, request: Request | None
) -> SignalCard:
    """Apply an officer's edit. A returned card goes back to confirmation once it was actually changed."""
    if card.status not in EDITABLE_STATUSES:
        raise invalid_status()
    before = audit.snapshot(card)
    sections = copy.deepcopy(card.sections)
    if patch.sections is not None:
        if patch.sections.scheme_payments is not None:
            sections["scheme_payments"] = patch.sections.scheme_payments.model_dump(mode="json")
        if patch.sections.proposed_measures is not None:
            sections["proposed_measures"] = [
                measure.value for measure in dict.fromkeys(patch.sections.proposed_measures)
            ]
        if patch.sections.note is not None:
            sections["note"] = patch.sections.note
    recipient = patch.recipient if patch.recipient is not None else card.recipient
    review_days = patch.review_days if patch.review_days is not None else card.review_days
    sections["route"] = {"recipient": recipient.value if recipient else None, "review_days": review_days}

    if sections == card.sections and recipient == card.recipient and review_days == card.review_days:
        return card
    card.sections = sections
    card.recipient = recipient
    card.review_days = review_days
    if card.status is SignalStatus.returned:
        card.status = SignalStatus.requires_confirmation
    session.flush()
    session.refresh(card)
    audit.record(session, user, "signal_card.update", "signal_card", card.id, before, audit.snapshot(card), request)
    return card


# ---------------------------------------------------------------- visibility


def card_stmt(user: AppUser, scope: TerritoryScope) -> Select[SignalCard, str, Zone | None, str, bool]:
    """Cards the user may see with the object data a row needs. Staff see their territory; a receiving
    body sees only cards addressed to it that were actually sent."""
    stmt = (
        select(
            SignalCard, ConstructionObject.name, ConstructionObject.zone, Territory.timezone, ConstructionObject.is_demo
        )
        .join(ConstructionObject, ConstructionObject.id == SignalCard.object_id)
        .join(Territory, Territory.id == ConstructionObject.territory_id)
    )
    stmt = scope.restrict(stmt, ConstructionObject.territory_id)
    if user.role in ROLE_RECIPIENT:
        stmt = stmt.where(SignalCard.recipient == ROLE_RECIPIENT[user.role], SignalCard.status.in_(DELIVERED_STATUSES))
    return stmt


def get_card_view(
    session: Session, user: AppUser, scope: TerritoryScope, card_id: int, *, lock: bool = False
) -> CardView:
    stmt = card_stmt(user, scope).where(SignalCard.id == card_id)
    if lock:
        stmt = stmt.with_for_update(of=SignalCard)
    row = session.execute(stmt).first()
    if row is None:
        raise api_error(404, "signal_not_found", "Сигнальная карточка не найдена")
    card, object_name, zone, timezone, is_demo = row
    return CardView(card=card, object_name=object_name, zone=zone, timezone=timezone, is_demo=is_demo)


def to_row(view: CardView, now: datetime | None = None) -> SignalRow:
    card = view.card
    overdue = (
        card.status is SignalStatus.sent
        and card.due_date is not None
        and card.due_date < local_today(view.timezone, now)
    )
    return SignalRow(
        id=card.id,
        number=card.number,
        object_id=card.object_id,
        object_name=view.object_name,
        zone=view.zone,
        status=card.status,
        recipient=card.recipient,
        due_date=card.due_date,
        is_overdue=overdue,
        is_demo=view.is_demo,
        created_at=card.created_at,
    )


def to_detail(session: Session, user: AppUser, view: CardView) -> SignalDetail:
    card = view.card
    # The audit log is not open to receiving bodies (SPEC section 4).
    audit_entries: list[SignalAuditEntry] = []
    if user.role in (Role.admin, Role.mio_officer):
        rows = session.execute(
            select(AuditLog, AppUser.username)
            .outerjoin(AppUser, AppUser.id == AuditLog.user_id)
            .where(AuditLog.entity_type == "signal_card", AuditLog.entity_id == card.id)
            .order_by(AuditLog.at, AuditLog.id)
        )
        audit_entries = [
            SignalAuditEntry(
                id=entry.id,
                user_id=entry.user_id,
                username=username,
                at=entry.at,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                before=entry.before,
                after=entry.after,
            )
            for entry, username in rows
        ]
    return SignalDetail(
        **to_row(view).model_dump(),
        origin=card.origin,
        sections=card.sections,
        review_days=card.review_days or 0,
        sent_at=card.sent_at,
        sent_by=card.sent_by,
        sent_pdf_evidence_id=session.scalar(
            select(func.min(Evidence.id)).where(Evidence.signal_card_id == card.id, Evidence.kind == EvidenceKind.pdf)
        ),
        return_comment=card.return_comment,
        response_text=card.response_text,
        response_at=card.response_at,
        responded_by=card.responded_by,
        created_by=card.created_by,
        audit=audit_entries,
    )


# ---------------------------------------------------------------- transitions


def _object(session: Session, card: SignalCard) -> ConstructionObject:
    obj = session.get(ConstructionObject, card.object_id)
    if obj is None:
        raise ValueError(f"signal card {card.id} refers to a missing object")
    return obj


def _payload(card: SignalCard, object_name: str) -> dict[str, Any]:
    return {
        "number": card.number,
        "object_id": card.object_id,
        "object_name": object_name,
        "due_date": _iso(card.due_date),
    }


def confirm_and_send(
    session: Session,
    view: CardView,
    user: AppUser,
    recipient: Recipient,
    request: Request | None,
    now: datetime | None = None,
) -> SignalCard:
    """The only path to `sent`. Fixes the deadline: `review_days` working days from today in the object's territory."""
    card = view.card
    if card.status is not SignalStatus.requires_confirmation:
        raise invalid_status()
    now = now or datetime.now(UTC)
    before = audit.snapshot(card)
    card.recipient = recipient
    card.status = SignalStatus.sent
    card.sent_at = now
    card.sent_by = user.id
    card.due_date = add_working_days(session, local_today(view.timezone, now), card.review_days or 0)
    sections = copy.deepcopy(card.sections)
    sections["route"] = {"recipient": recipient.value, "review_days": card.review_days}
    card.sections = sections
    session.flush()
    session.refresh(card)
    audit.record(
        session, user, "signal_card.confirm_and_send", "signal_card", card.id, before, audit.snapshot(card), request
    )

    obj = _object(session, card)
    addressees = users_covering_territory(
        session, obj.territory_id, {RECIPIENT_ROLE[recipient]}, exclude_user_id=user.id
    )
    add_notifications(
        session, addressees, NotificationKind.signal_sent, "signal_card", card.id, _payload(card, view.object_name)
    )
    return card


def notify_archive_failed(session: Session, view: CardView, user: AppUser) -> None:
    """Tell the sender that the sent PDF could not be archived. The dispatch itself stands; the notification
    kind is the closest existing one (`capture_failed`), with `reason` telling it apart."""
    add_notifications(
        session,
        [user],
        NotificationKind.capture_failed,
        "signal_card",
        view.card.id,
        {**_payload(view.card, view.object_name), "reason": "pdf_archive"},
    )


def return_card(session: Session, view: CardView, user: AppUser, comment: str, request: Request | None) -> SignalCard:
    card = view.card
    if card.status is not SignalStatus.requires_confirmation:
        raise invalid_status()
    before = audit.snapshot(card)
    card.status = SignalStatus.returned
    card.return_comment = comment
    session.flush()
    session.refresh(card)
    audit.record(session, user, "signal_card.return", "signal_card", card.id, before, audit.snapshot(card), request)

    # The author reworks the card; an automatic draft has none, so every officer of the territory is told.
    obj = _object(session, card)
    author = session.get(AppUser, card.created_by) if card.created_by else None
    if author is not None and author.is_active and author.role is Role.mio_officer:
        addressees = [author] if author.id != user.id else []
    else:
        addressees = users_covering_territory(session, obj.territory_id, {Role.mio_officer}, exclude_user_id=user.id)
    add_notifications(
        session, addressees, NotificationKind.signal_returned, "signal_card", card.id, _payload(card, view.object_name)
    )
    return card


def may_respond(user: AppUser, card: SignalCard) -> bool:
    """A receiving body answers cards addressed to it; a card addressed to the MIO itself is answered by
    a mio officer (OPEN_QUESTIONS #15)."""
    if user.role is Role.mio_officer:
        return card.recipient is Recipient.mio
    return ROLE_RECIPIENT.get(user.role) == card.recipient


def respond(
    session: Session,
    view: CardView,
    user: AppUser,
    response_text: str,
    request: Request | None,
    now: datetime | None = None,
) -> SignalCard:
    card = view.card
    if not may_respond(user, card):
        raise forbidden("Результат по этой карточке вносит другой орган")
    if card.status is not SignalStatus.sent:
        raise invalid_status()
    before = audit.snapshot(card)
    card.status = SignalStatus.responded
    card.response_text = response_text
    card.response_at = now or datetime.now(UTC)
    card.responded_by = user.id
    session.flush()
    session.refresh(card)
    audit.record(session, user, "signal_card.respond", "signal_card", card.id, before, audit.snapshot(card), request)

    obj = _object(session, card)
    add_notifications(
        session,
        users_covering_territory(session, obj.territory_id, {Role.mio_officer}, exclude_user_id=user.id),
        NotificationKind.signal_responded,
        "signal_card",
        card.id,
        _payload(card, view.object_name),
    )
    return card


def close_card(session: Session, view: CardView, user: AppUser, request: Request | None) -> SignalCard:
    card = view.card
    if card.status is not SignalStatus.responded:
        raise invalid_status()
    before = audit.snapshot(card)
    card.status = SignalStatus.closed
    session.flush()
    session.refresh(card)
    audit.record(session, user, "signal_card.close", "signal_card", card.id, before, audit.snapshot(card), request)
    return card


# ---------------------------------------------------------------- deadlines


def check_deadlines(session: Session, now: datetime | None = None) -> int:
    """Notify about cards that wait for an answer (SPEC 7.2) and return the number of notifications created.

    `signal_due_soon` starts one working day before the deadline and `signal_overdue` once the deadline has
    passed. Each user gets each of them once per card, so a repeated run (or a delayed one) adds nothing.
    """
    now = now or datetime.now(UTC)
    rows = session.execute(
        select(SignalCard, ConstructionObject, Territory.timezone)
        .join(ConstructionObject, ConstructionObject.id == SignalCard.object_id)
        .join(Territory, Territory.id == ConstructionObject.territory_id)
        .where(SignalCard.status == SignalStatus.sent, SignalCard.due_date.is_not(None))
        .order_by(SignalCard.id)
    ).all()
    if not rows:
        return 0
    overrides = load_overrides(session)
    already = {
        (entity_id, kind, user_id)
        for entity_id, kind, user_id in session.execute(
            select(Notification.entity_id, Notification.kind, Notification.user_id).where(
                Notification.entity_type == "signal_card",
                Notification.kind.in_([NotificationKind.signal_due_soon, NotificationKind.signal_overdue]),
                Notification.entity_id.in_([card.id for card, _, _ in rows]),
            )
        )
    }
    created = 0
    for card, obj, timezone in rows:
        if card.due_date is None:
            continue
        today = local_today(timezone, now)
        if card.due_date < today:
            kind = NotificationKind.signal_overdue
        elif shift_working_days(card.due_date, -1, overrides) <= today:
            kind = NotificationKind.signal_due_soon
        else:
            continue
        roles = {Role.mio_officer}
        if card.recipient is not None:
            roles.add(RECIPIENT_ROLE[card.recipient])
        addressees = [
            user
            for user in users_covering_territory(session, obj.territory_id, roles)
            if (card.id, kind, user.id) not in already
        ]
        created += add_notifications(session, addressees, kind, "signal_card", card.id, _payload(card, obj.name))
    return created

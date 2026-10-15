"""Risk scoring rules (SPEC section 6) as pure functions over plain data.

Nothing here touches the database: `service.py` loads the rows, converts them to the dataclasses below
and persists the `Evaluation`. Zone and key status follow rules over boolean facts; the numeric score
(weights from the `risk_factor` table) only orders objects and explains the picture.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.models.enums import (
    CheckStatus,
    ComplaintStatus,
    ConstructionStatus,
    DetectedBy,
    DocType,
    KeyStatus,
    PaymentScheme,
    PhraseCategory,
    Zone,
)
from app.modules.settings.service import AppSettings

PERMIT_DOC_TYPES = (DocType.dsu_permit, DocType.guarantee)
MONEY_OFFER_CATEGORIES = frozenset(
    {
        PhraseCategory.booking,
        PhraseCategory.down_payment,
        PhraseCategory.deposit,
        PhraseCategory.installment,
        PhraseCategory.preliminary_contract,
        PhraseCategory.covert_contract,
        PhraseCategory.price_before_completion,
    }
)
COVERT_CONTRACT_CATEGORIES = frozenset({PhraseCategory.covert_contract, PhraseCategory.preliminary_contract})

SCORE_MIN = 0
SCORE_MAX = 100
# Breakdown rows are a summary, not an index: a busy object can have hundreds of publications.
MAX_EVIDENCE_REFS = 20


@dataclass(frozen=True)
class DocumentFact:
    id: int
    doc_type: DocType
    check_status: CheckStatus


@dataclass(frozen=True)
class HitFact:
    category: PhraseCategory
    detected_by: DetectedBy
    confirmed: bool | None


@dataclass(frozen=True)
class AdFact:
    """A publication linked to the object inside the analysis window."""

    id: int
    payment_schemes: tuple[str, ...] = ()
    price_before_completion: bool = False
    hits: tuple[HitFact, ...] = ()


@dataclass(frozen=True)
class ComplaintFact:
    id: int
    is_collective: bool
    status: ComplaintStatus
    confirmed_payments: bool


@dataclass(frozen=True)
class InspectionFact:
    id: int
    inspected_at: date


@dataclass(frozen=True)
class ObjectFact:
    construction_status: ConstructionStatus
    planned_completion: date | None
    forecast_completion: date | None
    stalled_since: date | None
    readiness_actual_pct: int | None
    readiness_claimed_pct: int | None


@dataclass(frozen=True)
class ScoringInput:
    """Everything the rules need. `ads` are already limited to the analysis window."""

    obj: ObjectFact
    documents: Sequence[DocumentFact]
    ads: Sequence[AdFact]
    complaints: Sequence[ComplaintFact]
    latest_inspection: InspectionFact | None


@dataclass(frozen=True)
class FactorWeight:
    code: str
    weight: int


@dataclass(frozen=True)
class FactorOutcome:
    triggered: bool
    evidence: list[dict[str, Any]]
    detail: dict[str, Any]


@dataclass(frozen=True)
class Facts:
    """Boolean facts of SPEC 6.2 plus the data the breakdown refers to."""

    permit_confirmed: bool
    permit_checking: bool
    money_offer: bool
    covert_contract: bool
    confirmed_payments: bool
    overdue: bool
    stalled: bool
    complaints: bool
    readiness_overstated: bool
    active_ads: bool
    on_schedule: bool
    outcomes: dict[str, FactorOutcome]


@dataclass(frozen=True)
class Evaluation:
    score: int
    zone: Zone
    zone_reasons: list[str]
    key_status: KeyStatus
    key_status_detail: dict[str, int] | None
    breakdown: list[dict[str, Any]]
    facts: Facts


def _refs(type_: str, ids: Sequence[int]) -> list[dict[str, Any]]:
    return [{"type": type_, "id": item} for item in ids[:MAX_EVIDENCE_REFS]]


def counting_hit(hit: HitFact) -> bool:
    """Dictionary hits count until a person rejects them; LLM guesses count only once confirmed."""
    if hit.detected_by is DetectedBy.llm:
        return hit.confirmed is True
    return hit.confirmed is not False


def _no_permit(data: ScoringInput) -> FactorOutcome:
    permits = [doc for doc in data.documents if doc.doc_type in PERMIT_DOC_TYPES]
    confirmed = any(doc.check_status is CheckStatus.confirmed for doc in permits)
    return FactorOutcome(
        triggered=not confirmed,
        evidence=_refs("document", [doc.id for doc in permits]),
        detail={
            "doc_types": [doc_type.value for doc_type in PERMIT_DOC_TYPES],
            "count": len(permits),
            "checking": any(doc.check_status is CheckStatus.checking for doc in permits),
        },
    )


def _money_offer(data: ScoringInput, settings: AppSettings) -> tuple[FactorOutcome, bool]:
    """The factor outcome and the covert-contract fact (it rests on the same publications)."""
    categories: set[str] = set()
    schemes: set[str] = set()
    ad_ids: list[int] = []
    for ad in data.ads:
        ad_categories = {
            hit.category.value for hit in ad.hits if counting_hit(hit) and hit.category in MONEY_OFFER_CATEGORIES
        }
        if ad.price_before_completion:
            ad_categories.add(PhraseCategory.price_before_completion.value)
        if not (ad_categories or ad.payment_schemes):
            continue
        ad_ids.append(ad.id)
        categories |= ad_categories
        schemes |= set(ad.payment_schemes)
    covert = bool(categories & {category.value for category in COVERT_CONTRACT_CATEGORIES}) or (
        PaymentScheme.nonstandard_contract.value in schemes
    )
    outcome = FactorOutcome(
        triggered=bool(ad_ids),
        evidence=_refs("ad_post", ad_ids),
        detail={
            "window_days": settings.ad_window_days,
            "count": len(ad_ids),
            "categories": sorted(categories),
            "payment_schemes": sorted(schemes),
        },
    )
    return outcome, covert


def _active_ads(data: ScoringInput, settings: AppSettings) -> FactorOutcome:
    return FactorOutcome(
        triggered=bool(data.ads),
        evidence=_refs("ad_post", [ad.id for ad in data.ads]),
        detail={"window_days": settings.ad_window_days, "count": len(data.ads)},
    )


def _complaints(data: ScoringInput, settings: AppSettings) -> FactorOutcome:
    """Only complaints that are not closed count, collective ones and the open-count threshold alike."""
    open_ones = [item for item in data.complaints if item.status is not ComplaintStatus.closed]
    collective = [item for item in open_ones if item.is_collective]
    return FactorOutcome(
        triggered=bool(collective) or len(open_ones) >= settings.complaints_threshold,
        evidence=_refs("complaint", sorted((item.id for item in open_ones), reverse=True)),
        detail={
            "count": len(data.complaints),
            "open_count": len(open_ones),
            "collective_count": len(collective),
            "threshold": settings.complaints_threshold,
        },
    )


def _readiness_overstated(data: ScoringInput, settings: AppSettings) -> FactorOutcome:
    claimed, actual = data.obj.readiness_claimed_pct, data.obj.readiness_actual_pct
    gap = claimed - actual if claimed is not None and actual is not None else None
    return FactorOutcome(
        triggered=gap is not None and gap >= settings.readiness_gap_pp,
        evidence=_refs("inspection", [data.latest_inspection.id] if data.latest_inspection else []),
        detail={"claimed_pct": claimed, "actual_pct": actual, "gap_pp": gap, "threshold": settings.readiness_gap_pp},
    )


def _on_schedule(data: ScoringInput, settings: AppSettings, today: date) -> FactorOutcome:
    obj, inspection = data.obj, data.latest_inspection
    days_since_inspection = (today - inspection.inspected_at).days if inspection else None
    on_track = (
        obj.planned_completion is not None
        and obj.forecast_completion is not None
        and obj.forecast_completion <= obj.planned_completion
    )
    fresh = days_since_inspection is not None and days_since_inspection <= settings.stalled_days
    return FactorOutcome(
        triggered=obj.construction_status is ConstructionStatus.active and on_track and fresh,
        evidence=_refs("inspection", [inspection.id] if inspection else []),
        detail={
            "construction_status": obj.construction_status.value,
            "planned_completion": obj.planned_completion.isoformat() if obj.planned_completion else None,
            "forecast_completion": obj.forecast_completion.isoformat() if obj.forecast_completion else None,
            "stalled_days": days_since_inspection,
            "threshold": settings.stalled_days,
        },
    )


def is_overdue(obj: ObjectFact, today: date) -> bool:
    if obj.construction_status is ConstructionStatus.completed:
        return False
    delayed_forecast = (
        obj.planned_completion is not None
        and obj.forecast_completion is not None
        and obj.forecast_completion > obj.planned_completion
    )
    return delayed_forecast or (obj.planned_completion is not None and obj.planned_completion < today)


def compute_facts(data: ScoringInput, settings: AppSettings, today: date) -> Facts:
    no_permit = _no_permit(data)
    money_offer, covert_contract = _money_offer(data, settings)
    complaints = _complaints(data, settings)
    readiness = _readiness_overstated(data, settings)
    active_ads = _active_ads(data, settings)
    on_schedule = _on_schedule(data, settings, today)
    return Facts(
        permit_confirmed=not no_permit.triggered,
        permit_checking=any(
            doc.doc_type in PERMIT_DOC_TYPES and doc.check_status is CheckStatus.checking for doc in data.documents
        ),
        money_offer=money_offer.triggered,
        covert_contract=covert_contract,
        confirmed_payments=any(item.confirmed_payments for item in data.complaints),
        overdue=is_overdue(data.obj, today),
        stalled=data.obj.construction_status is ConstructionStatus.stalled,
        complaints=complaints.triggered,
        readiness_overstated=readiness.triggered,
        active_ads=active_ads.triggered,
        on_schedule=on_schedule.triggered,
        outcomes={
            "no_permit": no_permit,
            "money_offer": money_offer,
            "active_ads": active_ads,
            "complaints": complaints,
            "readiness_overstated": readiness,
            "on_schedule": on_schedule,
        },
    )


def decide_zone(facts: Facts) -> tuple[Zone, list[str]]:
    """Zone by rules (SPEC 6.2) and the codes of the conditions that decided it."""
    no_permit_at_all = not facts.permit_confirmed and not facts.permit_checking
    red_conditions = [
        code
        for code, active in (
            ("money_offer", facts.money_offer),
            ("covert_contract", facts.covert_contract),
            ("confirmed_payments", facts.confirmed_payments),
        )
        if active
    ]
    if no_permit_at_all and red_conditions:
        return Zone.red, ["no_permit", *red_conditions]

    problems = [
        code
        for code, active in (
            ("overdue", facts.overdue),
            ("stalled", facts.stalled),
            ("complaints", facts.complaints),
            ("readiness_overstated", facts.readiness_overstated),
        )
        if active
    ]
    if facts.permit_confirmed and not problems:
        return Zone.green, ["permit_confirmed"]

    reasons = [
        code
        for code, active in (
            ("no_permit", no_permit_at_all),
            ("permit_checking", not facts.permit_confirmed and facts.permit_checking),
            ("money_offer", facts.money_offer),
            ("covert_contract", facts.covert_contract),
            ("confirmed_payments", facts.confirmed_payments),
            *((code, True) for code in problems),
            ("active_ads", facts.active_ads),
        )
        if active
    ]
    return Zone.yellow, reasons


def decide_key_status(facts: Facts, obj: ObjectFact, today: date) -> tuple[KeyStatus, dict[str, int] | None]:
    """First matching code by priority (SPEC 6.4). `no_permit*` mean no permit and none under check."""
    no_permit_at_all = not facts.permit_confirmed and not facts.permit_checking
    if no_permit_at_all and facts.money_offer:
        return KeyStatus.no_permit_with_offer, None
    if no_permit_at_all:
        return KeyStatus.no_permit, None
    if not facts.permit_confirmed and facts.permit_checking:
        return KeyStatus.permit_checking, None
    if facts.money_offer:
        return KeyStatus.money_offer, None
    if facts.stalled:
        detail = {"stalled_days": (today - obj.stalled_since).days} if obj.stalled_since else None
        return KeyStatus.stalled, detail
    if facts.overdue:
        return KeyStatus.overdue, None
    if facts.complaints:
        return KeyStatus.complaints, None
    if facts.readiness_overstated:
        return KeyStatus.readiness_overstated, None
    return KeyStatus.ok, None


def evaluate(data: ScoringInput, factors: Sequence[FactorWeight], settings: AppSettings, today: date) -> Evaluation:
    """`factors` are the active factors in display order; their codes without a rule are not scored."""
    facts = compute_facts(data, settings, today)
    breakdown: list[dict[str, Any]] = []
    total = 0
    for factor in factors:
        outcome = facts.outcomes.get(factor.code)
        if outcome is None:
            continue
        breakdown.append(
            {
                "code": factor.code,
                "weight": factor.weight,
                "triggered": outcome.triggered,
                "evidence": outcome.evidence,
                "detail": outcome.detail,
            }
        )
        if outcome.triggered:
            total += factor.weight
    zone, zone_reasons = decide_zone(facts)
    key_status, key_status_detail = decide_key_status(facts, data.obj, today)
    return Evaluation(
        score=max(SCORE_MIN, min(SCORE_MAX, total)),
        zone=zone,
        zone_reasons=zone_reasons,
        key_status=key_status,
        key_status_detail=key_status_detail,
        breakdown=breakdown,
        facts=facts,
    )

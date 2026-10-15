"""Risk scoring rules (SPEC section 6, the Codemasters 8.0 case model) as pure functions over plain data.

Nothing here touches the database: `service.py` loads the rows, converts them to the dataclasses below
and persists the `Evaluation`. The result is deterministic: the same confirmed data always gives the same score.

Principles of the model:
- "no data" is not "no legal basis": unknown facts score nothing and are listed as `needs_check` flags;
- an AI hypothesis (an LLM finding nobody confirmed) is never a fact;
- the score is the sum of the weights of the triggered factors; the zone follows the score, and red also
  needs both R1 (no legal basis) and R2 (an offer to pay money).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.models.enums import (
    AdStatus,
    CheckStatus,
    ComplaintStatus,
    ConstructionStatus,
    DetectedBy,
    DocType,
    KeyStatus,
    LegalBasisStatus,
    PhraseCategory,
    Zone,
)
from app.modules.settings.service import AppSettings

R1 = "r1_no_legal_basis"
R2 = "r2_money_offer"
R3 = "r3_active_ads"
R4 = "r4_collective_complaint"
R5 = "r5_readiness_mismatch"
R6 = "r6_stalled_or_delayed"

FACTOR_LABELS = {R1: "R1", R2: "R2", R3: "R3", R4: "R4", R5: "R5", R6: "R6"}

# The two documents that give a legal basis for attracting money of share-holders (SPEC 6.0).
LEGAL_BASIS_DOC_TYPES = (DocType.guarantee, DocType.dsu_permit)
MONEY_OFFER_CATEGORIES = frozenset(
    {
        PhraseCategory.booking,
        PhraseCategory.down_payment,
        PhraseCategory.deposit,
        PhraseCategory.installment,
        PhraseCategory.preliminary_contract,
        PhraseCategory.covert_contract,
    }
)

# `needs_check` flag codes (SPEC 6.1).
LEGAL_BASIS_UNKNOWN = "legal_basis_unknown"
COMPLAINT_UNVERIFIED = "complaint_unverified"
READINESS_UNVERIFIED = "readiness_unverified"
AI_HYPOTHESES_PENDING = "ai_hypotheses_pending"
LINK_UNVERIFIED = "link_unverified"

# How a phrase hit is presented: a fact, a hypothesis of the AI, or something an analyst rejected.
HIT_FACT = "fact"
HIT_AI_HYPOTHESIS = "ai_hypothesis"
HIT_REJECTED = "rejected"

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
    id: int = 0
    fragment: str = ""


@dataclass(frozen=True)
class AdFact:
    """A publication linked to the object inside the analysis window."""

    id: int
    payment_schemes: tuple[str, ...] = ()
    hits: tuple[HitFact, ...] = ()
    status: AdStatus = AdStatus.captured
    claimed_readiness_pct: int | None = None


@dataclass(frozen=True)
class ComplaintFact:
    id: int
    is_collective: bool
    status: ComplaintStatus
    confirmed_payments: bool = False
    is_verified: bool = False


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
    """What the rules established, before weights are applied."""

    legal_basis_status: LegalBasisStatus
    outcomes: dict[str, FactorOutcome]
    needs_check: list[dict[str, Any]]
    stalled: bool
    delayed: bool


@dataclass(frozen=True)
class Evaluation:
    score: int
    zone: Zone
    zone_reasons: list[str]
    key_status: KeyStatus
    key_status_detail: dict[str, int] | None
    legal_basis_status: LegalBasisStatus
    needs_check: list[dict[str, Any]]
    breakdown: dict[str, Any]
    facts: Facts


def _refs(type_: str, ids: Sequence[int]) -> list[dict[str, Any]]:
    return [{"type": type_, "id": item} for item in ids[:MAX_EVIDENCE_REFS]]


def hit_kind(hit: HitFact) -> str:
    """Dictionary matches are facts about the text until an analyst rejects them; an LLM finding is only
    a hypothesis until an analyst confirms it."""
    if hit.confirmed is False:
        return HIT_REJECTED
    if hit.detected_by is DetectedBy.llm and hit.confirmed is None:
        return HIT_AI_HYPOTHESIS
    return HIT_FACT


# ---------------------------------------------------------------- legal basis (6.0)


def document_statuses(documents: Sequence[DocumentFact]) -> dict[str, str]:
    """Per document type of the legal basis: confirmed > checking > not_found > none (no record)."""
    order = (CheckStatus.confirmed, CheckStatus.checking, CheckStatus.not_found)
    result: dict[str, str] = {}
    for doc_type in LEGAL_BASIS_DOC_TYPES:
        present = {doc.check_status for doc in documents if doc.doc_type is doc_type}
        result[doc_type.value] = next((status.value for status in order if status in present), "none")
    return result


def legal_basis_status(documents: Sequence[DocumentFact]) -> LegalBasisStatus:
    statuses = document_statuses(documents)
    if CheckStatus.confirmed.value in statuses.values():
        return LegalBasisStatus.confirmed
    if all(status == CheckStatus.not_found.value for status in statuses.values()):
        return LegalBasisStatus.absent_established
    return LegalBasisStatus.unknown


# ---------------------------------------------------------------- factors (6.1)


def _r1(data: ScoringInput, status: LegalBasisStatus) -> FactorOutcome:
    documents = [doc for doc in data.documents if doc.doc_type in LEGAL_BASIS_DOC_TYPES]
    return FactorOutcome(
        triggered=status is LegalBasisStatus.absent_established,
        evidence=_refs("document", [doc.id for doc in documents]),
        detail={"legal_basis_status": status.value, "checks": document_statuses(data.documents)},
    )


def _r2(data: ScoringInput, settings: AppSettings) -> FactorOutcome:
    evidence: list[dict[str, Any]] = []
    categories: set[str] = set()
    schemes: set[str] = set()
    ad_ids: list[int] = []
    for ad in data.ads:
        facts = [hit for hit in ad.hits if hit_kind(hit) == HIT_FACT and hit.category in MONEY_OFFER_CATEGORIES]
        if not (facts or ad.payment_schemes):
            continue
        ad_ids.append(ad.id)
        categories |= {hit.category.value for hit in facts}
        schemes |= set(ad.payment_schemes)
        if facts:
            evidence += [
                {"type": "ad_post", "id": ad.id, "phrase_hit_id": hit.id, "fragment": hit.fragment} for hit in facts
            ]
        else:
            evidence.append({"type": "ad_post", "id": ad.id})
    return FactorOutcome(
        triggered=bool(ad_ids),
        evidence=evidence[:MAX_EVIDENCE_REFS],
        detail={
            "window_days": settings.ad_window_days,
            "count": len(ad_ids),
            "categories": sorted(categories),
            "payment_schemes": sorted(schemes),
        },
    )


def _r3(data: ScoringInput, settings: AppSettings) -> FactorOutcome:
    completed = data.obj.construction_status is ConstructionStatus.completed
    return FactorOutcome(
        triggered=bool(data.ads) and not completed,
        evidence=_refs("ad_post", [ad.id for ad in data.ads]),
        detail={
            "window_days": settings.ad_window_days,
            "count": len(data.ads),
            "construction_status": data.obj.construction_status.value,
        },
    )


def _open_collective(data: ScoringInput) -> list[ComplaintFact]:
    return [c for c in data.complaints if c.is_collective and c.status is not ComplaintStatus.closed]


def _r4(data: ScoringInput) -> FactorOutcome:
    collective = _open_collective(data)
    verified = [item for item in collective if item.is_verified]
    return FactorOutcome(
        triggered=bool(verified),
        evidence=_refs("complaint", sorted((item.id for item in verified), reverse=True)),
        detail={
            "count": len(data.complaints),
            "collective_count": len(collective),
            "verified_count": len(verified),
            "unverified_count": len(collective) - len(verified),
        },
    )


def _r5(data: ScoringInput, settings: AppSettings) -> FactorOutcome:
    """Both values need a source with a date: a publication with a confirmed claim and a photo inspection."""
    claimed, actual = data.obj.readiness_claimed_pct, data.obj.readiness_actual_pct
    claim_ads = [ad for ad in data.ads if ad.claimed_readiness_pct is not None]
    inspection = data.latest_inspection
    sourced = claimed is not None and actual is not None and bool(claim_ads) and inspection is not None
    gap = claimed - actual if claimed is not None and actual is not None else None
    evidence = _refs("inspection", [inspection.id] if inspection else []) + _refs(
        "ad_post", [ad.id for ad in claim_ads]
    )
    return FactorOutcome(
        triggered=sourced and gap is not None and gap >= settings.readiness_gap_pp,
        evidence=evidence[:MAX_EVIDENCE_REFS],
        detail={
            "claimed_pct": claimed,
            "actual_pct": actual,
            "gap_pp": gap,
            "threshold": settings.readiness_gap_pp,
            "sourced": sourced,
            "inspected_at": inspection.inspected_at.isoformat() if inspection else None,
        },
    )


def _delay_days(obj: ObjectFact, today: date) -> tuple[int | None, int | None]:
    """(forecast - planned, days since the planned date passed); None where the dates are missing."""
    forecast_delay = (
        (obj.forecast_completion - obj.planned_completion).days
        if obj.forecast_completion is not None and obj.planned_completion is not None
        else None
    )
    overdue = (today - obj.planned_completion).days if obj.planned_completion is not None else None
    return forecast_delay, overdue


def _r6(data: ScoringInput, settings: AppSettings, today: date) -> tuple[FactorOutcome, bool, bool]:
    obj = data.obj
    stalled_days = (today - obj.stalled_since).days if obj.stalled_since is not None else None
    stalled = (
        obj.construction_status is ConstructionStatus.stalled
        and stalled_days is not None
        and stalled_days >= settings.stalled_days
    )
    forecast_delay, overdue = _delay_days(obj, today)
    delayed = obj.construction_status is not ConstructionStatus.completed and (
        (forecast_delay is not None and forecast_delay >= settings.significant_delay_days)
        or (overdue is not None and overdue > settings.significant_delay_days)
    )
    outcome = FactorOutcome(
        triggered=stalled or delayed,
        evidence=[],
        detail={
            "construction_status": obj.construction_status.value,
            "stalled": stalled,
            "stalled_days": stalled_days,
            "stalled_threshold": settings.stalled_days,
            "delayed": delayed,
            "forecast_delay_days": forecast_delay,
            "planned_overdue_days": overdue if overdue is not None and overdue > 0 else None,
            "significant_delay_days": settings.significant_delay_days,
        },
    )
    return outcome, stalled, delayed


# ---------------------------------------------------------------- "needs check" flags


def _needs_check(data: ScoringInput, status: LegalBasisStatus) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if status is LegalBasisStatus.unknown:
        flags.append({"code": LEGAL_BASIS_UNKNOWN, "detail": {"checks": document_statuses(data.documents)}})
    unverified = [item.id for item in _open_collective(data) if not item.is_verified]
    if unverified:
        flags.append(
            {
                "code": COMPLAINT_UNVERIFIED,
                "detail": {"count": len(unverified), "complaint_ids": unverified[:MAX_EVIDENCE_REFS]},
            }
        )
    if data.obj.readiness_claimed_pct is not None and data.latest_inspection is None:
        flags.append({"code": READINESS_UNVERIFIED, "detail": {"claimed_pct": data.obj.readiness_claimed_pct}})
    pending = [(ad.id, hit.id) for ad in data.ads for hit in ad.hits if hit_kind(hit) == HIT_AI_HYPOTHESIS]
    if pending:
        flags.append(
            {
                "code": AI_HYPOTHESES_PENDING,
                "detail": {
                    "count": len(pending),
                    "ad_post_ids": sorted({ad_id for ad_id, _ in pending})[:MAX_EVIDENCE_REFS],
                },
            }
        )
    unlinked = [ad.id for ad in data.ads if ad.status is AdStatus.verification]
    if unlinked:
        flags.append(
            {"code": LINK_UNVERIFIED, "detail": {"count": len(unlinked), "ad_post_ids": unlinked[:MAX_EVIDENCE_REFS]}}
        )
    return flags


# ---------------------------------------------------------------- facts, zone, key status


def compute_facts(data: ScoringInput, settings: AppSettings, today: date) -> Facts:
    status = legal_basis_status(data.documents)
    r6, stalled, delayed = _r6(data, settings, today)
    return Facts(
        legal_basis_status=status,
        outcomes={
            R1: _r1(data, status),
            R2: _r2(data, settings),
            R3: _r3(data, settings),
            R4: _r4(data),
            R5: _r5(data, settings),
            R6: r6,
        },
        needs_check=_needs_check(data, status),
        stalled=stalled,
        delayed=delayed,
    )


def decide_zone(score: int, triggered: set[str], settings: AppSettings) -> tuple[Zone, list[str]]:
    """Zone by score (SPEC 6.2). Red additionally needs R1 and R2; a high score without them stays yellow."""
    red_min, yellow_min = settings.zone_red_min, settings.zone_yellow_min
    if score >= red_min:
        if {R1, R2} <= triggered:
            return Zone.red, ["r1_and_r2"]
        return Zone.yellow, [f"score_{red_min}_without_r1_r2"]
    if score >= yellow_min:
        return Zone.yellow, [f"score_{yellow_min}_{red_min - 1}"]
    return Zone.green, [f"score_0_{yellow_min - 1}"]


def decide_key_status(
    facts: Facts, triggered: set[str], obj: ObjectFact, today: date
) -> tuple[KeyStatus, dict[str, int] | None]:
    """First match by priority (SPEC 6.4)."""
    if {R1, R2} <= triggered:
        return KeyStatus.no_legal_basis_with_offer, None
    if R1 in triggered:
        return KeyStatus.no_legal_basis, None
    if R2 in triggered:
        return KeyStatus.money_offer, None
    if facts.legal_basis_status is LegalBasisStatus.unknown:
        return KeyStatus.legal_basis_unknown, None
    if facts.stalled:
        return KeyStatus.stalled, {"stalled_days": (today - obj.stalled_since).days} if obj.stalled_since else None
    if facts.delayed:
        return KeyStatus.delayed, None
    if R4 in triggered:
        return KeyStatus.collective_complaint, None
    if R5 in triggered:
        return KeyStatus.readiness_mismatch, None
    if R3 in triggered:
        return KeyStatus.active_ads, None
    return KeyStatus.ok, None


def evaluate(data: ScoringInput, factors: Sequence[FactorWeight], settings: AppSettings, today: date) -> Evaluation:
    """`factors` are the active factors in display order; their codes without a rule are not scored."""
    facts = compute_facts(data, settings, today)
    items: list[dict[str, Any]] = []
    total = 0
    triggered: set[str] = set()
    for factor in factors:
        outcome = facts.outcomes.get(factor.code)
        if outcome is None:
            continue
        items.append(
            {
                "code": factor.code,
                "label": FACTOR_LABELS[factor.code],
                "weight": factor.weight,
                "triggered": outcome.triggered,
                "evidence": outcome.evidence,
                "detail": outcome.detail,
            }
        )
        if outcome.triggered:
            total += factor.weight
            triggered.add(factor.code)
    score = max(SCORE_MIN, min(SCORE_MAX, total))
    zone, zone_reasons = decide_zone(score, triggered, settings)
    key_status, key_status_detail = decide_key_status(facts, triggered, data.obj, today)
    return Evaluation(
        score=score,
        zone=zone,
        zone_reasons=zone_reasons,
        key_status=key_status,
        key_status_detail=key_status_detail,
        legal_basis_status=facts.legal_basis_status,
        needs_check=facts.needs_check,
        breakdown={
            "factors": items,
            "needs_check": facts.needs_check,
            "legal_basis_status": facts.legal_basis_status.value,
        },
        facts=facts,
    )

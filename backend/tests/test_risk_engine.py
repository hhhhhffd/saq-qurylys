"""Pure scoring rules (SPEC section 6, case model): legal basis, factors R1-R6, zones, key status. No database."""

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest

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
from app.modules.risk import engine
from app.modules.risk.engine import (
    AdFact,
    ComplaintFact,
    DocumentFact,
    FactorWeight,
    HitFact,
    InspectionFact,
    ObjectFact,
    ScoringInput,
)
from app.modules.settings.service import AppSettings

TODAY = date(2026, 10, 13)
SETTINGS = AppSettings()
WEIGHTS = [
    FactorWeight(engine.R1, 35),
    FactorWeight(engine.R2, 25),
    FactorWeight(engine.R3, 10),
    FactorWeight(engine.R4, 15),
    FactorWeight(engine.R5, 10),
    FactorWeight(engine.R6, 5),
]

GUARANTEE_CONFIRMED = DocumentFact(1, DocType.guarantee, CheckStatus.confirmed)
PERMIT_CONFIRMED = DocumentFact(2, DocType.dsu_permit, CheckStatus.confirmed)
GUARANTEE_NOT_FOUND = DocumentFact(3, DocType.guarantee, CheckStatus.not_found)
PERMIT_NOT_FOUND = DocumentFact(4, DocType.dsu_permit, CheckStatus.not_found)
BOTH_NOT_FOUND = [GUARANTEE_NOT_FOUND, PERMIT_NOT_FOUND]

DEPOSIT_HIT = HitFact(PhraseCategory.deposit, DetectedBy.dictionary, None, id=301, fragment="внесите депозит")
BOOKING_AD = AdFact(55, hits=(DEPOSIT_HIT,))
PLAIN_AD = AdFact(56)


def make_input(**overrides: Any) -> ScoringInput:
    base = ScoringInput(
        obj=ObjectFact(
            construction_status=ConstructionStatus.active,
            planned_completion=None,
            forecast_completion=None,
            stalled_since=None,
            readiness_actual_pct=None,
            readiness_claimed_pct=None,
        ),
        documents=[],
        ads=[],
        complaints=[],
        latest_inspection=None,
    )
    obj_fields = {k: overrides.pop(k) for k in list(overrides) if k in ObjectFact.__dataclass_fields__}
    if obj_fields:
        overrides["obj"] = replace(base.obj, **obj_fields)
    return replace(base, **overrides)


def evaluate(
    data: ScoringInput, weights: list[FactorWeight] | None = None, settings: AppSettings = SETTINGS
) -> engine.Evaluation:
    return engine.evaluate(data, WEIGHTS if weights is None else weights, settings, TODAY)


def factor(result: engine.Evaluation, code: str) -> dict[str, Any]:
    return next(item for item in result.breakdown["factors"] if item["code"] == code)


def flags(result: engine.Evaluation) -> list[str]:
    return [item["code"] for item in result.needs_check]


def complaint(
    id_: int, *, collective: bool = True, verified: bool = True, status: ComplaintStatus = ComplaintStatus.new
) -> ComplaintFact:
    return ComplaintFact(id_, collective, status, False, verified)


# ---------------------------------------------------------------- mandatory scenarios A / B / C (SPEC 6.6)


def test_scenario_a_unknown_legal_basis_with_a_paid_booking_is_yellow() -> None:
    result = evaluate(make_input(ads=[BOOKING_AD]))  # the basis was never checked: no documents at all
    assert result.legal_basis_status is LegalBasisStatus.unknown
    assert not factor(result, engine.R1)["triggered"]
    assert factor(result, engine.R2)["triggered"] and factor(result, engine.R3)["triggered"]
    assert result.score == 35  # R2 25 + R3 10
    assert result.zone is Zone.yellow
    assert result.zone_reasons == ["score_25_59"]
    assert flags(result) == [engine.LEGAL_BASIS_UNKNOWN]
    assert result.key_status is KeyStatus.money_offer


def test_scenario_b_established_absence_of_the_basis_with_a_deposit_is_red() -> None:
    result = evaluate(make_input(documents=BOTH_NOT_FOUND, ads=[BOOKING_AD]))
    assert result.legal_basis_status is LegalBasisStatus.absent_established
    assert [factor(result, code)["triggered"] for code in (engine.R1, engine.R2, engine.R3)] == [True] * 3
    assert result.score == 70  # R1 35 + R2 25 + R3 10
    assert result.zone is Zone.red
    assert result.zone_reasons == ["r1_and_r2"]
    assert flags(result) == []
    assert result.key_status is KeyStatus.no_legal_basis_with_offer


def test_scenario_c_confirmed_guarantee_without_a_permit_and_plain_ads_is_green() -> None:
    result = evaluate(make_input(documents=[GUARANTEE_CONFIRMED], ads=[PLAIN_AD]))
    assert result.legal_basis_status is LegalBasisStatus.confirmed
    assert not factor(result, engine.R1)["triggered"]  # a missing MIO permit is not R1 when the guarantee stands
    assert factor(result, engine.R3)["triggered"] and not factor(result, engine.R2)["triggered"]
    assert result.score == 10
    assert result.zone is Zone.green
    assert result.zone_reasons == ["score_0_24"]
    assert flags(result) == []
    assert result.key_status is KeyStatus.active_ads


# ---------------------------------------------------------------- legal basis (6.0) and R1


@pytest.mark.parametrize(
    ("documents", "expected"),
    [
        ([], LegalBasisStatus.unknown),
        ([GUARANTEE_CONFIRMED], LegalBasisStatus.confirmed),
        ([PERMIT_CONFIRMED], LegalBasisStatus.confirmed),
        ([GUARANTEE_NOT_FOUND, PERMIT_CONFIRMED], LegalBasisStatus.confirmed),
        (BOTH_NOT_FOUND, LegalBasisStatus.absent_established),
        (
            [GUARANTEE_NOT_FOUND, PERMIT_NOT_FOUND, DocumentFact(9, DocType.psd, CheckStatus.confirmed)],
            LegalBasisStatus.absent_established,
        ),
        # Only one of the two types was checked: that proves nothing about the other.
        ([GUARANTEE_NOT_FOUND], LegalBasisStatus.unknown),
        ([PERMIT_NOT_FOUND], LegalBasisStatus.unknown),
        # A check that is still running keeps the status unknown.
        ([DocumentFact(5, DocType.dsu_permit, CheckStatus.checking)], LegalBasisStatus.unknown),
        ([GUARANTEE_NOT_FOUND, DocumentFact(5, DocType.dsu_permit, CheckStatus.checking)], LegalBasisStatus.unknown),
        (
            [GUARANTEE_NOT_FOUND, PERMIT_NOT_FOUND, DocumentFact(5, DocType.dsu_permit, CheckStatus.checking)],
            LegalBasisStatus.unknown,
        ),
        # Other documents are not a legal basis.
        ([DocumentFact(6, DocType.psd, CheckStatus.confirmed)], LegalBasisStatus.unknown),
    ],
)
def test_legal_basis_status(documents: list[DocumentFact], expected: LegalBasisStatus) -> None:
    assert engine.legal_basis_status(documents) is expected
    result = evaluate(make_input(documents=documents))
    assert factor(result, engine.R1)["triggered"] is (expected is LegalBasisStatus.absent_established)
    assert (engine.LEGAL_BASIS_UNKNOWN in flags(result)) is (expected is LegalBasisStatus.unknown)


def test_unknown_is_not_absent_and_scores_nothing() -> None:
    result = evaluate(make_input())
    assert result.score == 0
    assert result.zone is Zone.green
    assert flags(result) == [engine.LEGAL_BASIS_UNKNOWN]
    assert result.key_status is KeyStatus.legal_basis_unknown


def test_r1_evidence_and_detail() -> None:
    item = factor(
        evaluate(make_input(documents=[*BOTH_NOT_FOUND, DocumentFact(9, DocType.psd, CheckStatus.confirmed)])),
        engine.R1,
    )
    assert item["evidence"] == [{"type": "document", "id": 3}, {"type": "document", "id": 4}]
    assert item["detail"] == {
        "legal_basis_status": "absent_established",
        "checks": {"guarantee": "not_found", "dsu_permit": "not_found"},
    }


def test_legal_basis_unknown_flag_lists_what_was_checked() -> None:
    result = evaluate(
        make_input(documents=[GUARANTEE_NOT_FOUND, DocumentFact(5, DocType.dsu_permit, CheckStatus.checking)])
    )
    assert result.needs_check == [
        {"code": "legal_basis_unknown", "detail": {"checks": {"guarantee": "not_found", "dsu_permit": "checking"}}}
    ]


# ---------------------------------------------------------------- R2: an offer to pay money


@pytest.mark.parametrize("category", sorted(engine.MONEY_OFFER_CATEGORIES))
def test_every_money_category_is_an_offer(category: PhraseCategory) -> None:
    ad = AdFact(1, hits=(HitFact(category, DetectedBy.dictionary, None, id=1, fragment="x"),))
    assert factor(evaluate(make_input(ads=[ad])), engine.R2)["triggered"]


@pytest.mark.parametrize("category", [PhraseCategory.sales_start, PhraseCategory.price_before_completion])
def test_other_categories_are_not_an_offer(category: PhraseCategory) -> None:
    ad = AdFact(1, hits=(HitFact(category, DetectedBy.dictionary, None),))
    assert not factor(evaluate(make_input(ads=[ad])), engine.R2)["triggered"]


@pytest.mark.parametrize(
    ("hit", "r2", "kind"),
    [
        (HitFact(PhraseCategory.deposit, DetectedBy.dictionary, None), True, "fact"),  # not rejected: a fact
        (HitFact(PhraseCategory.deposit, DetectedBy.dictionary, True), True, "fact"),
        (HitFact(PhraseCategory.deposit, DetectedBy.dictionary, False), False, "rejected"),  # an analyst said no
        (HitFact(PhraseCategory.deposit, DetectedBy.llm, None), False, "ai_hypothesis"),  # a guess is not a fact
        (HitFact(PhraseCategory.deposit, DetectedBy.llm, False), False, "rejected"),
        (HitFact(PhraseCategory.deposit, DetectedBy.llm, True), True, "fact"),  # confirmed by an analyst
    ],
)
def test_phrase_hit_counts_as_a_fact_by_origin_and_confirmation(hit: HitFact, r2: bool, kind: str) -> None:
    assert engine.hit_kind(hit) == kind
    result = evaluate(make_input(ads=[AdFact(1, hits=(hit,))]))
    assert factor(result, engine.R2)["triggered"] is r2


def test_unconfirmed_llm_hit_is_not_r2_but_a_pending_hypothesis() -> None:
    guess = HitFact(PhraseCategory.deposit, DetectedBy.llm, None, id=7, fragment="внесите задаток")
    result = evaluate(make_input(documents=BOTH_NOT_FOUND, ads=[AdFact(5, hits=(guess,))]))
    assert not factor(result, engine.R2)["triggered"]
    assert result.zone is Zone.yellow  # R1 35 + R3 10 = 45: no red without R2
    assert flags(result) == [engine.AI_HYPOTHESES_PENDING]
    assert result.needs_check[0]["detail"] == {"count": 1, "ad_post_ids": [5]}


def test_rejected_dictionary_hit_is_neither_r2_nor_a_pending_hypothesis() -> None:
    result = evaluate(
        make_input(
            documents=[GUARANTEE_CONFIRMED],
            ads=[AdFact(5, hits=(HitFact(PhraseCategory.booking, DetectedBy.dictionary, False),))],
        )
    )
    assert not factor(result, engine.R2)["triggered"]
    assert flags(result) == []


def test_confirmed_payment_scheme_is_an_offer_without_a_phrase() -> None:
    item = factor(evaluate(make_input(ads=[AdFact(8, payment_schemes=("installment", "booking"))])), engine.R2)
    assert item["triggered"]
    assert item["evidence"] == [{"type": "ad_post", "id": 8}]
    assert item["detail"]["payment_schemes"] == ["booking", "installment"]


def test_r2_evidence_quotes_the_phrase() -> None:
    item = factor(evaluate(make_input(ads=[BOOKING_AD, PLAIN_AD])), engine.R2)
    assert item["evidence"] == [{"type": "ad_post", "id": 55, "phrase_hit_id": 301, "fragment": "внесите депозит"}]
    assert item["detail"] == {"window_days": 30, "count": 1, "categories": ["deposit"], "payment_schemes": []}


def test_r2_evidence_is_capped() -> None:
    ads = [
        AdFact(i, hits=(HitFact(PhraseCategory.booking, DetectedBy.dictionary, None, id=i, fragment="бронь"),))
        for i in range(1, 40)
    ]
    item = factor(evaluate(make_input(ads=ads)), engine.R2)
    assert len(item["evidence"]) == engine.MAX_EVIDENCE_REFS
    assert item["detail"]["count"] == 39


# ---------------------------------------------------------------- R3: active ads


def test_r3_needs_a_linked_publication_and_a_building_that_is_not_completed() -> None:
    assert not factor(evaluate(make_input()), engine.R3)["triggered"]
    assert factor(evaluate(make_input(ads=[PLAIN_AD])), engine.R3)["triggered"]
    completed = make_input(ads=[PLAIN_AD], construction_status=ConstructionStatus.completed)
    assert not factor(evaluate(completed), engine.R3)["triggered"]


def test_r3_counts_publications_whose_link_is_unverified_but_flags_them() -> None:
    result = evaluate(make_input(documents=[GUARANTEE_CONFIRMED], ads=[AdFact(1, status=AdStatus.verification)]))
    assert factor(result, engine.R3)["triggered"]
    assert flags(result) == [engine.LINK_UNVERIFIED]
    assert result.needs_check[0]["detail"] == {"count": 1, "ad_post_ids": [1]}


# ---------------------------------------------------------------- R4: verified collective complaint


@pytest.mark.parametrize(
    ("complaints", "r4", "expected_flags"),
    [
        ([], False, []),
        ([complaint(1)], True, []),
        ([complaint(1, status=ComplaintStatus.in_review)], True, []),
        ([complaint(1, verified=False)], False, [engine.COMPLAINT_UNVERIFIED]),  # not verified: a flag, no points
        ([complaint(1, status=ComplaintStatus.closed)], False, []),  # closed does not count
        ([complaint(1, verified=False, status=ComplaintStatus.closed)], False, []),  # nor ask for a check
        ([complaint(1, collective=False)], False, []),  # an individual complaint is not R4
        ([complaint(1, collective=False, verified=False)], False, []),
        ([complaint(1), complaint(2, verified=False)], True, [engine.COMPLAINT_UNVERIFIED]),
    ],
)
def test_r4_collective_complaint(complaints: list[ComplaintFact], r4: bool, expected_flags: list[str]) -> None:
    result = evaluate(make_input(documents=[GUARANTEE_CONFIRMED], complaints=complaints))
    assert factor(result, engine.R4)["triggered"] is r4
    assert flags(result) == expected_flags


def test_r4_evidence_and_detail() -> None:
    complaints = [complaint(1), complaint(2, verified=False), complaint(3), complaint(4, collective=False)]
    item = factor(evaluate(make_input(complaints=complaints)), engine.R4)
    assert item["evidence"] == [{"type": "complaint", "id": 3}, {"type": "complaint", "id": 1}]
    assert item["detail"] == {"count": 4, "collective_count": 3, "verified_count": 2, "unverified_count": 1}


# ---------------------------------------------------------------- R5: readiness mismatch


def _r5_input(claimed: int | None, actual: int | None, *, ad: bool = True, inspection: bool = True) -> ScoringInput:
    return make_input(
        documents=[GUARANTEE_CONFIRMED],
        readiness_claimed_pct=claimed,
        readiness_actual_pct=actual,
        ads=[AdFact(11, claimed_readiness_pct=claimed)] if ad else [],
        latest_inspection=InspectionFact(21, TODAY - timedelta(days=3)) if inspection else None,
    )


@pytest.mark.parametrize(
    ("claimed", "actual", "r5"), [(80, 60, True), (80, 61, False), (95, 10, True), (50, 70, False)]
)
def test_r5_gap_threshold(claimed: int, actual: int, r5: bool) -> None:
    assert factor(evaluate(_r5_input(claimed, actual)), engine.R5)["triggered"] is r5


def test_r5_gap_threshold_is_a_setting() -> None:
    result = evaluate(_r5_input(80, 70), settings=AppSettings(readiness_gap_pp=10))
    assert factor(result, engine.R5)["triggered"]


def test_r5_needs_both_sources() -> None:
    assert factor(evaluate(_r5_input(90, 30)), engine.R5)["triggered"]
    no_inspection = evaluate(_r5_input(90, 30, inspection=False))
    assert not factor(no_inspection, engine.R5)["triggered"]
    assert flags(no_inspection) == [engine.READINESS_UNVERIFIED]  # a claim without a photo inspection
    assert not factor(evaluate(_r5_input(90, 30, ad=False)), engine.R5)["triggered"]  # no publication behind the claim
    assert not factor(evaluate(_r5_input(None, 30)), engine.R5)["triggered"]
    assert not factor(evaluate(_r5_input(90, None)), engine.R5)["triggered"]


def test_r5_evidence_names_both_sources() -> None:
    item = factor(evaluate(_r5_input(90, 30)), engine.R5)
    assert item["evidence"] == [{"type": "inspection", "id": 21}, {"type": "ad_post", "id": 11}]
    assert item["detail"] == {
        "claimed_pct": 90,
        "actual_pct": 30,
        "gap_pp": 60,
        "threshold": 20,
        "sourced": True,
        "inspected_at": "2026-10-10",
    }


# ---------------------------------------------------------------- R6: stalled or delayed


def _stalled(days: int, **extra: Any) -> ScoringInput:
    return make_input(
        documents=[GUARANTEE_CONFIRMED],
        construction_status=ConstructionStatus.stalled,
        stalled_since=TODAY - timedelta(days=days),
        **extra,
    )


@pytest.mark.parametrize(("days", "r6"), [(45, True), (30, True), (29, False), (0, False)])
def test_r6_stalled_branch(days: int, r6: bool) -> None:
    result = evaluate(_stalled(days))
    assert factor(result, engine.R6)["triggered"] is r6
    assert (result.key_status is KeyStatus.stalled) is r6


def test_r6_stalled_without_a_date_is_not_established() -> None:
    result = evaluate(make_input(documents=[GUARANTEE_CONFIRMED], construction_status=ConstructionStatus.stalled))
    assert not factor(result, engine.R6)["triggered"]


def test_r6_stalled_threshold_is_a_setting() -> None:
    assert factor(evaluate(_stalled(10), settings=AppSettings(stalled_days=7)), engine.R6)["triggered"]


@pytest.mark.parametrize(
    ("planned", "forecast", "r6"),
    [
        (date(2027, 1, 1), date(2027, 4, 1), True),  # forecast is 90 days over the plan
        (date(2027, 1, 1), date(2027, 3, 31), False),  # 89 days
        (date(2027, 1, 1), date(2026, 12, 1), False),  # ahead of the plan
        (TODAY - timedelta(days=91), None, True),  # the plan passed more than 90 days ago
        (TODAY - timedelta(days=90), None, False),
        (TODAY - timedelta(days=200), TODAY + timedelta(days=30), True),
        (date(2027, 1, 1), None, False),
        (None, date(2027, 1, 1), False),
    ],
)
def test_r6_delayed_branch(planned: date | None, forecast: date | None, r6: bool) -> None:
    result = evaluate(
        make_input(documents=[GUARANTEE_CONFIRMED], planned_completion=planned, forecast_completion=forecast)
    )
    assert factor(result, engine.R6)["triggered"] is r6
    assert (result.key_status is KeyStatus.delayed) is r6


def test_r6_delay_threshold_is_a_setting() -> None:
    data = make_input(
        documents=[GUARANTEE_CONFIRMED], planned_completion=date(2027, 1, 1), forecast_completion=date(2027, 2, 1)
    )
    assert not factor(evaluate(data), engine.R6)["triggered"]
    assert factor(evaluate(data, settings=AppSettings(significant_delay_days=30)), engine.R6)["triggered"]


def test_a_completed_object_is_not_delayed() -> None:
    data = make_input(
        documents=[GUARANTEE_CONFIRMED],
        construction_status=ConstructionStatus.completed,
        planned_completion=date(2025, 1, 1),
        forecast_completion=date(2026, 1, 1),
    )
    assert not factor(evaluate(data), engine.R6)["triggered"]


def test_r6_detail() -> None:
    item = factor(evaluate(_stalled(45)), engine.R6)
    assert item["detail"]["stalled"] is True and item["detail"]["stalled_days"] == 45
    assert item["detail"]["delayed"] is False
    assert item["detail"]["stalled_threshold"] == 30 and item["detail"]["significant_delay_days"] == 90


def test_stalled_key_status_carries_the_downtime() -> None:
    result = evaluate(_stalled(45))
    assert result.key_status is KeyStatus.stalled
    assert result.key_status_detail == {"stalled_days": 45}


# ---------------------------------------------------------------- score and zones


def test_score_is_the_sum_of_triggered_weights_and_clamped() -> None:
    everything = make_input(
        documents=BOTH_NOT_FOUND,
        ads=[AdFact(55, hits=(DEPOSIT_HIT,), claimed_readiness_pct=90)],
        complaints=[complaint(1)],
        readiness_claimed_pct=90,
        readiness_actual_pct=30,
        latest_inspection=InspectionFact(21, TODAY),
        construction_status=ConstructionStatus.stalled,
        stalled_since=TODAY - timedelta(days=60),
    )
    assert evaluate(everything).score == 100  # 35 + 25 + 10 + 15 + 10 + 5
    heavier = [FactorWeight(engine.R1, 90), *WEIGHTS[1:]]
    assert evaluate(everything, heavier).score == 100


def test_score_never_goes_below_zero() -> None:
    result = evaluate(make_input(ads=[PLAIN_AD]), [FactorWeight(engine.R3, -20)])
    assert result.score == 0


@pytest.mark.parametrize(
    ("score", "zone", "reasons"),
    [
        (0, Zone.green, ["score_0_24"]),
        (24, Zone.green, ["score_0_24"]),
        (25, Zone.yellow, ["score_25_59"]),
        (59, Zone.yellow, ["score_25_59"]),
    ],
)
def test_zone_by_score(score: int, zone: Zone, reasons: list[str]) -> None:
    assert engine.decide_zone(score, set(), SETTINGS) == (zone, reasons)


def test_high_score_is_red_only_with_both_r1_and_r2() -> None:
    assert engine.decide_zone(60, {engine.R1, engine.R2}, SETTINGS) == (Zone.red, ["r1_and_r2"])
    assert engine.decide_zone(100, {engine.R1, engine.R2, engine.R3}, SETTINGS) == (Zone.red, ["r1_and_r2"])
    assert engine.decide_zone(60, {engine.R1}, SETTINGS) == (Zone.yellow, ["score_60_without_r1_r2"])
    assert engine.decide_zone(95, {engine.R2}, SETTINGS) == (Zone.yellow, ["score_60_without_r1_r2"])
    assert engine.decide_zone(100, set(), SETTINGS) == (Zone.yellow, ["score_60_without_r1_r2"])


def test_a_high_score_without_r1_and_r2_stays_yellow() -> None:
    # R2 25 + R3 10 + R4 15 + R5 10 + R6 5 = 65, but the legal basis is not known to be absent.
    data = make_input(
        ads=[AdFact(55, hits=(DEPOSIT_HIT,), claimed_readiness_pct=90)],
        complaints=[complaint(1)],
        readiness_claimed_pct=90,
        readiness_actual_pct=30,
        latest_inspection=InspectionFact(21, TODAY),
        construction_status=ConstructionStatus.stalled,
        stalled_since=TODAY - timedelta(days=60),
    )
    result = evaluate(data)
    assert result.score == 65
    assert (result.zone, result.zone_reasons) == (Zone.yellow, ["score_60_without_r1_r2"])


def test_r1_and_r2_with_a_low_total_is_not_red() -> None:
    lighter = [FactorWeight(engine.R1, 20), FactorWeight(engine.R2, 20), FactorWeight(engine.R3, 10)]
    result = evaluate(make_input(documents=BOTH_NOT_FOUND, ads=[BOOKING_AD]), lighter)
    assert result.score == 50
    assert (result.zone, result.zone_reasons) == (Zone.yellow, ["score_25_59"])


def test_thresholds_come_from_settings() -> None:
    settings = AppSettings(zone_yellow_min=10, zone_red_min=40)
    assert engine.decide_zone(9, set(), settings) == (Zone.green, ["score_0_9"])
    assert engine.decide_zone(10, set(), settings) == (Zone.yellow, ["score_10_39"])
    assert engine.decide_zone(40, {engine.R1, engine.R2}, settings)[0] is Zone.red
    result = evaluate(make_input(documents=[GUARANTEE_CONFIRMED], ads=[PLAIN_AD]), settings=settings)
    assert (result.score, result.zone) == (10, Zone.yellow)


def test_red_needs_active_factors_r1_and_r2() -> None:
    data = make_input(documents=BOTH_NOT_FOUND, ads=[BOOKING_AD])
    assert evaluate(data).zone is Zone.red
    without_r1 = [w for w in WEIGHTS if w.code != engine.R1]  # a deactivated factor did not fire
    assert evaluate(data, without_r1).zone is Zone.yellow


def test_the_evaluation_is_deterministic() -> None:
    data = make_input(documents=BOTH_NOT_FOUND, ads=[BOOKING_AD, PLAIN_AD], complaints=[complaint(1, verified=False)])
    first, second = evaluate(data), evaluate(data)
    assert first.breakdown == second.breakdown
    assert (first.score, first.zone, first.zone_reasons, first.key_status) == (
        second.score,
        second.zone,
        second.zone_reasons,
        second.key_status,
    )


# ---------------------------------------------------------------- breakdown shape


def test_breakdown_lists_every_given_factor_with_label_and_weight_even_when_not_triggered() -> None:
    result = evaluate(make_input(documents=[GUARANTEE_CONFIRMED]))
    breakdown = result.breakdown
    assert set(breakdown) == {"factors", "needs_check", "legal_basis_status"}
    assert breakdown["legal_basis_status"] == "confirmed"
    assert [(item["code"], item["label"], item["weight"], item["triggered"]) for item in breakdown["factors"]] == [
        ("r1_no_legal_basis", "R1", 35, False),
        ("r2_money_offer", "R2", 25, False),
        ("r3_active_ads", "R3", 10, False),
        ("r4_collective_complaint", "R4", 15, False),
        ("r5_readiness_mismatch", "R5", 10, False),
        ("r6_stalled_or_delayed", "R6", 5, False),
    ]
    assert all(
        {"code", "label", "weight", "triggered", "evidence", "detail"} == item.keys() for item in breakdown["factors"]
    )
    assert breakdown["needs_check"] == result.needs_check == []


def test_only_given_factors_are_scored_and_unknown_codes_are_skipped() -> None:
    weights = [FactorWeight(engine.R3, 10), FactorWeight("on_schedule", -15), FactorWeight("something_new", 99)]
    result = evaluate(make_input(ads=[PLAIN_AD]), weights)
    assert [item["code"] for item in result.breakdown["factors"]] == [engine.R3]
    assert result.score == 10


def test_flags_are_independent_of_factor_weights() -> None:
    result = evaluate(make_input(), [])
    assert flags(result) == [engine.LEGAL_BASIS_UNKNOWN]
    assert result.breakdown["factors"] == []


# ---------------------------------------------------------------- key status


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"documents": BOTH_NOT_FOUND, "ads": [BOOKING_AD]}, KeyStatus.no_legal_basis_with_offer),
        ({"documents": BOTH_NOT_FOUND}, KeyStatus.no_legal_basis),
        ({"documents": BOTH_NOT_FOUND, "ads": [PLAIN_AD]}, KeyStatus.no_legal_basis),
        ({"documents": [GUARANTEE_CONFIRMED], "ads": [BOOKING_AD]}, KeyStatus.money_offer),
        ({"ads": [BOOKING_AD]}, KeyStatus.money_offer),
        ({}, KeyStatus.legal_basis_unknown),
        ({"ads": [PLAIN_AD]}, KeyStatus.legal_basis_unknown),
        ({"documents": [GUARANTEE_CONFIRMED], "complaints": [complaint(1)]}, KeyStatus.collective_complaint),
        ({"documents": [GUARANTEE_CONFIRMED], "ads": [PLAIN_AD]}, KeyStatus.active_ads),
        ({"documents": [GUARANTEE_CONFIRMED]}, KeyStatus.ok),
    ],
)
def test_key_status(overrides: dict[str, Any], expected: KeyStatus) -> None:
    assert evaluate(make_input(**overrides)).key_status is expected


def test_key_status_priority_order() -> None:
    base = {
        "documents": [GUARANTEE_CONFIRMED],
        "complaints": [complaint(1)],
        "ads": [PLAIN_AD],
        "planned_completion": TODAY - timedelta(days=200),
        "construction_status": ConstructionStatus.stalled,
        "stalled_since": TODAY - timedelta(days=60),
    }
    assert evaluate(make_input(**base)).key_status is KeyStatus.stalled
    base["construction_status"] = ConstructionStatus.active
    assert evaluate(make_input(**base)).key_status is KeyStatus.delayed
    base["planned_completion"] = None
    assert evaluate(make_input(**base)).key_status is KeyStatus.collective_complaint
    base["complaints"] = []
    assert evaluate(make_input(**base)).key_status is KeyStatus.active_ads


def test_readiness_mismatch_key_status() -> None:
    result = evaluate(_r5_input(90, 30))
    assert result.key_status is KeyStatus.readiness_mismatch
    assert result.zone is Zone.green  # R5 10 only

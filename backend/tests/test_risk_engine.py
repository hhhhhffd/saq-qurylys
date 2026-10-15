"""Pure scoring rules (SPEC section 6): factors, clamping, zone rules and key status. No database."""

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest

from app.models.enums import (
    CheckStatus,
    ComplaintStatus,
    ConstructionStatus,
    DetectedBy,
    DocType,
    KeyStatus,
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
DEFAULT_WEIGHTS = [
    FactorWeight("no_permit", 40),
    FactorWeight("money_offer", 20),
    FactorWeight("active_ads", 15),
    FactorWeight("complaints", 15),
    FactorWeight("readiness_overstated", 10),
    FactorWeight("on_schedule", -15),
]
CONFIRMED_PERMIT = DocumentFact(1, DocType.dsu_permit, CheckStatus.confirmed)
BOOKING_HIT = HitFact(PhraseCategory.booking, DetectedBy.dictionary, None)


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


def evaluate(data: ScoringInput, weights: list[FactorWeight] | None = None) -> engine.Evaluation:
    return engine.evaluate(data, weights if weights is not None else DEFAULT_WEIGHTS, SETTINGS, TODAY)


def factor(result: engine.Evaluation, code: str) -> dict[str, Any]:
    return next(item for item in result.breakdown if item["code"] == code)


# ---------------------------------------------------------------- factors


@pytest.mark.parametrize(
    ("documents", "triggered"),
    [
        ([], True),
        ([DocumentFact(1, DocType.dsu_permit, CheckStatus.confirmed)], False),
        ([DocumentFact(1, DocType.guarantee, CheckStatus.confirmed)], False),
        ([DocumentFact(1, DocType.dsu_permit, CheckStatus.checking)], True),
        ([DocumentFact(1, DocType.dsu_permit, CheckStatus.not_found)], True),
        ([DocumentFact(1, DocType.psd, CheckStatus.confirmed)], True),  # other documents are not a permit
        (
            [
                DocumentFact(1, DocType.dsu_permit, CheckStatus.not_found),
                DocumentFact(2, DocType.guarantee, CheckStatus.confirmed),
            ],
            False,
        ),
    ],
)
def test_no_permit_factor(documents: list[DocumentFact], triggered: bool) -> None:
    result = evaluate(make_input(documents=documents))
    assert factor(result, "no_permit")["triggered"] is triggered


def test_no_permit_evidence_lists_permit_documents_only() -> None:
    documents = [CONFIRMED_PERMIT, DocumentFact(2, DocType.psd, CheckStatus.confirmed)]
    item = factor(evaluate(make_input(documents=documents)), "no_permit")
    assert item["evidence"] == [{"type": "document", "id": 1}]
    assert item["detail"]["doc_types"] == ["dsu_permit", "guarantee"]


@pytest.mark.parametrize(
    ("ad", "triggered"),
    [
        (AdFact(1, hits=(BOOKING_HIT,)), True),
        (AdFact(1, hits=(HitFact(PhraseCategory.booking, DetectedBy.dictionary, True),)), True),
        (AdFact(1, hits=(HitFact(PhraseCategory.booking, DetectedBy.dictionary, False),)), False),  # rejected
        (AdFact(1, hits=(HitFact(PhraseCategory.booking, DetectedBy.llm, None),)), False),  # an unconfirmed guess
        (AdFact(1, hits=(HitFact(PhraseCategory.booking, DetectedBy.llm, False),)), False),
        (AdFact(1, hits=(HitFact(PhraseCategory.booking, DetectedBy.llm, True),)), True),
        (AdFact(1, hits=(HitFact(PhraseCategory.sales_start, DetectedBy.dictionary, None),)), False),
        (AdFact(1, payment_schemes=("installment",)), True),
        (AdFact(1, price_before_completion=True), True),
        (AdFact(1), False),
    ],
)
def test_money_offer_factor(ad: AdFact, triggered: bool) -> None:
    result = evaluate(make_input(ads=[ad]))
    assert factor(result, "money_offer")["triggered"] is triggered
    assert result.facts.money_offer is triggered


@pytest.mark.parametrize(
    "category",
    [
        PhraseCategory.booking,
        PhraseCategory.down_payment,
        PhraseCategory.deposit,
        PhraseCategory.installment,
        PhraseCategory.preliminary_contract,
        PhraseCategory.covert_contract,
        PhraseCategory.price_before_completion,
    ],
)
def test_every_money_category_counts(category: PhraseCategory) -> None:
    ad = AdFact(1, hits=(HitFact(category, DetectedBy.dictionary, None),))
    assert evaluate(make_input(ads=[ad])).facts.money_offer


def test_money_offer_detail_and_evidence() -> None:
    ads = [
        AdFact(7, payment_schemes=("booking", "installment"), hits=(BOOKING_HIT,)),
        AdFact(8),
        AdFact(9, hits=(HitFact(PhraseCategory.deposit, DetectedBy.dictionary, False),)),
    ]
    item = factor(evaluate(make_input(ads=ads)), "money_offer")
    assert item["evidence"] == [{"type": "ad_post", "id": 7}]
    assert item["detail"] == {
        "window_days": 7,
        "count": 1,
        "categories": ["booking"],
        "payment_schemes": ["booking", "installment"],
    }


@pytest.mark.parametrize(
    ("ads", "expected"),
    [
        ([], False),
        ([AdFact(1)], True),
    ],
)
def test_active_ads_factor(ads: list[AdFact], expected: bool) -> None:
    item = factor(evaluate(make_input(ads=ads)), "active_ads")
    assert item["triggered"] is expected
    assert item["detail"]["count"] == len(ads)


def _complaint(id_: int, *, collective: bool = False, status: ComplaintStatus = ComplaintStatus.new) -> ComplaintFact:
    return ComplaintFact(id_, collective, status, False)


@pytest.mark.parametrize(
    ("complaints", "triggered"),
    [
        ([], False),
        ([_complaint(1, collective=True)], True),
        ([_complaint(1, collective=True, status=ComplaintStatus.in_review)], True),
        ([_complaint(1, collective=True, status=ComplaintStatus.closed)], False),  # closed ones do not count at all
        ([_complaint(1, collective=True, status=ComplaintStatus.closed), _complaint(2)], False),
        ([_complaint(1), _complaint(2)], False),
        ([_complaint(1), _complaint(2), _complaint(3)], True),
        ([_complaint(1), _complaint(2, status=ComplaintStatus.in_review), _complaint(3)], True),
        ([_complaint(1), _complaint(2), _complaint(3, status=ComplaintStatus.closed)], False),  # closed do not count
    ],
)
def test_complaints_factor(complaints: list[ComplaintFact], triggered: bool) -> None:
    assert factor(evaluate(make_input(complaints=complaints)), "complaints")["triggered"] is triggered


def test_closed_collective_complaint_does_not_hold_an_object_out_of_green() -> None:
    data = make_input(
        documents=[CONFIRMED_PERMIT], complaints=[_complaint(1, collective=True, status=ComplaintStatus.closed)]
    )
    result = evaluate(data)
    assert result.zone is Zone.green
    assert result.key_status is KeyStatus.ok
    item = factor(result, "complaints")
    assert item["evidence"] == []
    assert item["detail"] == {"count": 1, "open_count": 0, "collective_count": 0, "threshold": 3}


def test_complaints_evidence_lists_open_complaints_only() -> None:
    complaints = [_complaint(1, status=ComplaintStatus.closed), _complaint(2, collective=True), _complaint(3)]
    item = factor(evaluate(make_input(complaints=complaints)), "complaints")
    assert item["evidence"] == [{"type": "complaint", "id": 3}, {"type": "complaint", "id": 2}]
    assert item["detail"]["collective_count"] == 1


def test_complaints_threshold_comes_from_settings() -> None:
    data = make_input(complaints=[_complaint(1), _complaint(2)])
    result = engine.evaluate(data, DEFAULT_WEIGHTS, AppSettings(complaints_threshold=2), TODAY)
    item = factor(result, "complaints")
    assert item["triggered"] is True
    assert item["detail"] == {"count": 2, "open_count": 2, "collective_count": 0, "threshold": 2}


@pytest.mark.parametrize(
    ("claimed", "actual", "triggered"),
    [(60, 50, True), (59, 50, False), (90, 10, True), (None, 50, False), (60, None, False), (40, 50, False)],
)
def test_readiness_overstated_factor(claimed: int | None, actual: int | None, triggered: bool) -> None:
    data = make_input(readiness_claimed_pct=claimed, readiness_actual_pct=actual)
    item = factor(evaluate(data), "readiness_overstated")
    assert item["triggered"] is triggered
    expected_gap = claimed - actual if claimed is not None and actual is not None else None
    assert item["detail"]["gap_pp"] == expected_gap


def _on_schedule_input(**overrides: Any) -> ScoringInput:
    values: dict[str, Any] = {
        "construction_status": ConstructionStatus.active,
        "planned_completion": date(2027, 6, 30),
        "forecast_completion": date(2027, 6, 30),
        "latest_inspection": InspectionFact(5, TODAY - timedelta(days=30)),
    }
    return make_input(**{**values, **overrides})


@pytest.mark.parametrize(
    ("overrides", "triggered"),
    [
        ({}, True),
        ({"forecast_completion": date(2027, 1, 1)}, True),
        ({"forecast_completion": date(2027, 7, 1)}, False),  # later than planned
        ({"forecast_completion": None}, False),
        ({"planned_completion": None}, False),
        ({"construction_status": ConstructionStatus.stalled}, False),
        ({"construction_status": ConstructionStatus.not_started}, False),
        ({"construction_status": ConstructionStatus.completed}, False),
        ({"latest_inspection": InspectionFact(5, TODAY - timedelta(days=31))}, False),  # photo is too old
        ({"latest_inspection": None}, False),
    ],
)
def test_on_schedule_factor(overrides: dict[str, Any], triggered: bool) -> None:
    result = evaluate(_on_schedule_input(**overrides))
    assert factor(result, "on_schedule")["triggered"] is triggered


def test_on_schedule_reports_inspection_age_and_evidence() -> None:
    item = factor(evaluate(_on_schedule_input()), "on_schedule")
    assert item["detail"]["stalled_days"] == 30
    assert item["detail"]["threshold"] == 30
    assert item["evidence"] == [{"type": "inspection", "id": 5}]


def test_breakdown_lists_every_given_factor_with_weight_even_when_not_triggered() -> None:
    result = evaluate(make_input())
    assert [item["code"] for item in result.breakdown] == [w.code for w in DEFAULT_WEIGHTS]
    assert {item["code"]: item["weight"] for item in result.breakdown}["on_schedule"] == -15
    assert all({"code", "weight", "triggered", "evidence", "detail"} <= item.keys() for item in result.breakdown)


def test_only_given_factors_are_scored_and_unknown_codes_are_skipped() -> None:
    weights = [FactorWeight("no_permit", 40), FactorWeight("something_new", 99)]
    result = evaluate(make_input(), weights)
    assert [item["code"] for item in result.breakdown] == ["no_permit"]
    assert result.score == 40


def test_evidence_references_are_capped() -> None:
    ads = [AdFact(index) for index in range(1, 60)]
    item = factor(evaluate(make_input(ads=ads)), "active_ads")
    assert len(item["evidence"]) == engine.MAX_EVIDENCE_REFS
    assert item["detail"]["count"] == 59


# ---------------------------------------------------------------- score


def test_score_is_the_sum_of_triggered_weights() -> None:
    data = make_input(ads=[AdFact(1, hits=(BOOKING_HIT,))], complaints=[_complaint(1, collective=True)])
    assert evaluate(data).score == 40 + 20 + 15 + 15


def test_score_is_clamped_to_100() -> None:
    data = make_input(
        ads=[AdFact(1, hits=(BOOKING_HIT,))],
        complaints=[_complaint(1, collective=True)],
        readiness_claimed_pct=90,
        readiness_actual_pct=10,
    )
    assert evaluate(data).score == 100  # 40 + 20 + 15 + 15 + 10 is exactly 100
    heavier = [FactorWeight("no_permit", 90), *DEFAULT_WEIGHTS[1:]]
    assert evaluate(data, heavier).score == 100


def test_score_is_clamped_to_zero() -> None:
    data = _on_schedule_input(documents=[CONFIRMED_PERMIT])
    result = evaluate(data)
    assert factor(result, "on_schedule")["triggered"]
    assert result.score == 0  # only the -15 factor fired


def test_negative_factor_lowers_the_score() -> None:
    data = _on_schedule_input(ads=[AdFact(1)])  # no permit (+40), ads (+15), on schedule (-15)
    assert evaluate(data).score == 40


# ---------------------------------------------------------------- zones


def test_red_without_permit_and_with_money_offer() -> None:
    result = evaluate(make_input(ads=[AdFact(1, hits=(BOOKING_HIT,))]))
    assert result.zone is Zone.red
    assert result.zone_reasons == ["no_permit", "money_offer"]


def test_red_without_permit_and_with_covert_contract() -> None:
    hit = HitFact(PhraseCategory.covert_contract, DetectedBy.dictionary, None)
    result = evaluate(make_input(ads=[AdFact(1, hits=(hit,))]))
    assert result.zone is Zone.red
    assert result.zone_reasons == ["no_permit", "money_offer", "covert_contract"]


def test_red_through_nonstandard_contract_scheme() -> None:
    result = evaluate(make_input(ads=[AdFact(1, payment_schemes=("nonstandard_contract",))]))
    assert result.zone is Zone.red
    assert result.facts.covert_contract


def test_red_without_permit_and_with_confirmed_payments_only() -> None:
    result = evaluate(make_input(complaints=[ComplaintFact(1, False, ComplaintStatus.closed, True)]))
    assert result.zone is Zone.red
    assert result.zone_reasons == ["no_permit", "confirmed_payments"]


def test_permit_under_check_is_never_red() -> None:
    documents = [DocumentFact(1, DocType.dsu_permit, CheckStatus.checking)]
    data = make_input(
        documents=documents,
        ads=[AdFact(1, hits=(BOOKING_HIT,))],
        complaints=[ComplaintFact(1, True, ComplaintStatus.new, True)],
    )
    result = evaluate(data)
    assert result.zone is Zone.yellow
    assert "permit_checking" in result.zone_reasons


def test_no_permit_without_a_money_offer_is_yellow() -> None:
    result = evaluate(make_input(ads=[AdFact(1)]))
    assert result.zone is Zone.yellow
    assert result.zone_reasons == ["no_permit", "active_ads"]


def test_no_permit_and_nothing_else_is_yellow() -> None:
    result = evaluate(make_input())
    assert result.zone is Zone.yellow
    assert result.zone_reasons == ["no_permit"]


def test_confirmed_permit_and_clean_is_green() -> None:
    result = evaluate(make_input(documents=[CONFIRMED_PERMIT]))
    assert result.zone is Zone.green
    assert result.zone_reasons == ["permit_confirmed"]


def test_confirmed_permit_with_a_money_offer_is_still_green() -> None:
    result = evaluate(make_input(documents=[CONFIRMED_PERMIT], ads=[AdFact(1, hits=(BOOKING_HIT,))]))
    assert result.zone is Zone.green


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"construction_status": ConstructionStatus.stalled}, "stalled"),
        ({"planned_completion": date(2026, 1, 1)}, "overdue"),
        ({"planned_completion": date(2027, 1, 1), "forecast_completion": date(2027, 3, 1)}, "overdue"),
        ({"complaints": [_complaint(1, collective=True)]}, "complaints"),
        ({"readiness_claimed_pct": 80, "readiness_actual_pct": 20}, "readiness_overstated"),
    ],
)
def test_confirmed_permit_with_a_problem_is_yellow(overrides: dict[str, Any], reason: str) -> None:
    result = evaluate(make_input(documents=[CONFIRMED_PERMIT], **overrides))
    assert result.zone is Zone.yellow
    assert result.zone_reasons == [reason]


def test_completed_object_is_not_overdue() -> None:
    data = make_input(
        documents=[CONFIRMED_PERMIT],
        construction_status=ConstructionStatus.completed,
        planned_completion=date(2025, 1, 1),
    )
    assert not evaluate(data).facts.overdue
    assert evaluate(data).zone is Zone.green


def test_zone_does_not_depend_on_weights_or_active_factors() -> None:
    data = make_input(ads=[AdFact(1, hits=(BOOKING_HIT,))])
    assert evaluate(data, []).zone is Zone.red
    assert evaluate(data, [FactorWeight("no_permit", 0)]).zone is Zone.red


# ---------------------------------------------------------------- key status


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"ads": [AdFact(1, hits=(BOOKING_HIT,))]}, KeyStatus.no_permit_with_offer),
        ({}, KeyStatus.no_permit),
        ({"complaints": [ComplaintFact(1, False, ComplaintStatus.new, True)]}, KeyStatus.no_permit),
        (
            {
                "documents": [DocumentFact(1, DocType.guarantee, CheckStatus.checking)],
                "ads": [AdFact(1, hits=(BOOKING_HIT,))],
            },
            KeyStatus.permit_checking,
        ),
        ({"documents": [CONFIRMED_PERMIT], "ads": [AdFact(1, hits=(BOOKING_HIT,))]}, KeyStatus.money_offer),
        (
            {"documents": [CONFIRMED_PERMIT], "construction_status": ConstructionStatus.stalled},
            KeyStatus.stalled,
        ),
        ({"documents": [CONFIRMED_PERMIT], "planned_completion": date(2026, 1, 1)}, KeyStatus.overdue),
        ({"documents": [CONFIRMED_PERMIT], "complaints": [_complaint(1, collective=True)]}, KeyStatus.complaints),
        (
            {"documents": [CONFIRMED_PERMIT], "readiness_claimed_pct": 80, "readiness_actual_pct": 20},
            KeyStatus.readiness_overstated,
        ),
        ({"documents": [CONFIRMED_PERMIT]}, KeyStatus.ok),
    ],
)
def test_key_status(overrides: dict[str, Any], expected: KeyStatus) -> None:
    assert evaluate(make_input(**overrides)).key_status is expected


def test_key_status_priority_order() -> None:
    everything = make_input(
        documents=[CONFIRMED_PERMIT],
        ads=[AdFact(1, hits=(BOOKING_HIT,))],
        complaints=[_complaint(1, collective=True)],
        construction_status=ConstructionStatus.stalled,
        planned_completion=date(2026, 1, 1),
        readiness_claimed_pct=80,
        readiness_actual_pct=20,
    )
    assert evaluate(everything).key_status is KeyStatus.money_offer
    no_ads = replace(everything, ads=[])
    assert evaluate(no_ads).key_status is KeyStatus.stalled
    not_stalled = make_input(
        documents=[CONFIRMED_PERMIT],
        complaints=[_complaint(1, collective=True)],
        planned_completion=date(2026, 1, 1),
        readiness_claimed_pct=80,
        readiness_actual_pct=20,
    )
    assert evaluate(not_stalled).key_status is KeyStatus.overdue


def test_stalled_key_status_carries_the_days_since_stalled_since() -> None:
    data = make_input(
        documents=[CONFIRMED_PERMIT],
        construction_status=ConstructionStatus.stalled,
        stalled_since=TODAY - timedelta(days=45),
    )
    result = evaluate(data)
    assert result.key_status is KeyStatus.stalled
    assert result.key_status_detail == {"stalled_days": 45}


def test_stalled_without_a_date_has_no_detail() -> None:
    data = make_input(documents=[CONFIRMED_PERMIT], construction_status=ConstructionStatus.stalled)
    assert evaluate(data).key_status_detail is None

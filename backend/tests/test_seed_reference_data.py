from sqlalchemy import select
from sqlalchemy.orm import Session

from app import seed
from app.models import Phrase, RiskFactor, RiskFactorChange
from app.models.enums import PhraseCategory


def _old_factor(code: str, weight: int) -> RiskFactor:
    return RiskFactor(code=code, description="старый фактор", weight=weight, sort_order=1)


def test_obsolete_risk_factors_are_removed_or_switched_off(db: Session) -> None:
    """Dev databases made before the case model hold the old factor codes."""
    db.add_all([_old_factor("no_permit", 40), _old_factor("money_offer", 20), _old_factor("on_schedule", -15)])
    db.add(RiskFactorChange(code="money_offer", old_weight=20, new_weight=25, old_active=True, new_active=True))
    db.flush()

    seed.seed_reference(db)
    seed.seed_reference(db)  # repeating changes nothing

    factors = {factor.code: factor for factor in db.scalars(select(RiskFactor))}
    assert "no_permit" not in factors and "on_schedule" not in factors  # nothing referred to them
    assert factors["money_offer"].is_active is False  # its weight history must stay readable
    assert {factor.code for factor in factors.values() if factor.is_active} == {
        "r1_no_legal_basis",
        "r2_money_offer",
        "r3_active_ads",
        "r4_collective_complaint",
        "r5_readiness_mismatch",
        "r6_stalled_or_delayed",
    }


def test_existing_dictionary_gets_the_added_variants_and_keeps_its_edits(db: Session) -> None:
    deposit = Phrase(
        category=PhraseCategory.deposit, text="задаток", variants=["внести задаток", "мой вариант"], weight=77
    )
    db.add(deposit)
    db.flush()

    seed.seed_reference(db)
    seed.seed_reference(db)

    db.refresh(deposit)
    assert deposit.variants == ["внести задаток", "мой вариант", "внести депозит", "оплатить депозит"]
    assert deposit.weight == 77
    completion = next(p for p in db.scalars(select(Phrase)) if p.category is PhraseCategory.price_before_completion)
    assert "цена до завершения" in completion.variants

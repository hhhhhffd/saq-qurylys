from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app import audit
from app.deps import GlobalAdmin, PageDep, ScopeDep, SessionDep, StaffUser
from app.errors import api_error
from app.events import objects_changed
from app.models import AppUser, ConstructionObject, RiskFactor, RiskFactorChange, RiskScore
from app.models.enums import ScoreTrigger
from app.modules.objects.service import get_object_in_scope
from app.modules.risk import service
from app.modules.risk.schemas import (
    RiskFactorChangeOut,
    RiskFactorOut,
    RiskFactorUpdate,
    ScoreHistoryItem,
)
from app.schemas import Page

router = APIRouter(tags=["risk"])


@router.get("/objects/{object_id}/score-history", response_model=Page[ScoreHistoryItem])
def score_history(
    object_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep, page: PageDep
) -> Page[ScoreHistoryItem]:
    """Calculations of the object, newest first."""
    get_object_in_scope(session, scope, object_id)
    stmt = select(RiskScore).where(RiskScore.object_id == object_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(RiskScore.calculated_at.desc(), RiskScore.id.desc()).limit(page.limit).offset(page.offset)
    )
    return Page(items=[ScoreHistoryItem.model_validate(row) for row in rows], total=total)


@router.post("/objects/{object_id}/recalculate", response_model=ScoreHistoryItem)
def recalculate_object(object_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep) -> ScoreHistoryItem:
    get_object_in_scope(session, scope, object_id)
    result = service.recalculate(session, object_id, ScoreTrigger.manual)
    if result is None:
        raise api_error(404, "object_not_found", "Объект не найден")
    item = ScoreHistoryItem.model_validate(result.risk_score)
    session.commit()
    if result.entered_red:
        service.dispatch_red_zone(object_id)
    return item


@router.get("/risk-factors", response_model=list[RiskFactorOut])
def list_risk_factors(session: SessionDep, user: StaffUser) -> list[RiskFactor]:
    return list(session.scalars(select(RiskFactor).order_by(RiskFactor.sort_order, RiskFactor.code)))


@router.get("/risk-factors/history", response_model=Page[RiskFactorChangeOut])
def risk_factor_history(session: SessionDep, user: StaffUser, page: PageDep) -> Page[RiskFactorChangeOut]:
    total = session.scalar(select(func.count()).select_from(RiskFactorChange)) or 0
    rows = session.execute(
        select(RiskFactorChange, AppUser.full_name)
        .outerjoin(AppUser, AppUser.id == RiskFactorChange.changed_by)
        .order_by(RiskFactorChange.changed_at.desc(), RiskFactorChange.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    items = [
        RiskFactorChangeOut(
            id=change.id,
            code=change.code,
            old_weight=change.old_weight,
            new_weight=change.new_weight,
            old_active=change.old_active,
            new_active=change.new_active,
            changed_by=change.changed_by,
            changed_by_name=full_name,
            changed_at=change.changed_at,
        )
        for change, full_name in rows
    ]
    return Page(items=items, total=total)


@router.patch("/risk-factors/{code}", response_model=RiskFactorOut)
def update_risk_factor(
    code: str, body: RiskFactorUpdate, session: SessionDep, user: GlobalAdmin, scope: ScopeDep, request: Request
) -> RiskFactor:
    """Weights are country-wide, hence the global admin. A change of weight or activity is recorded in the
    history and every object is rescored afterwards (asynchronously, through the usual change event)."""
    factor = session.get(RiskFactor, code)
    if factor is None:
        raise api_error(404, "risk_factor_not_found", "Фактор риска не найден")
    before = audit.snapshot(factor)
    old_weight, old_active = factor.weight, factor.is_active
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(factor, field, value)
    scoring_changed = factor.weight != old_weight or factor.is_active != old_active
    if scoring_changed:
        session.add(
            RiskFactorChange(
                code=code,
                old_weight=old_weight,
                new_weight=factor.weight,
                old_active=old_active,
                new_active=factor.is_active,
                changed_by=user.id,
            )
        )
    session.flush()
    session.refresh(factor)
    audit.record(session, user, "risk_factor.update", "risk_factor", None, before, audit.snapshot(factor), request)
    object_ids = (
        list(session.scalars(scope.restrict(select(ConstructionObject.id), ConstructionObject.territory_id)))
        if scoring_changed
        else []
    )
    session.commit()
    objects_changed(object_ids)
    return factor

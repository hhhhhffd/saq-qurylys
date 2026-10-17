from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from sqlalchemy import Date, Select, and_, func, select
from sqlalchemy.orm import Session, aliased

from app import audit
from app.deps import PageDep, ScopeDep, SessionDep, StaffUser
from app.errors import api_error, forbidden
from app.models import AppUser, Assignment, ConstructionObject, Territory
from app.models.enums import AssignmentStatus, NotificationKind, Role
from app.modules.assignments.schemas import (
    AssigneeOut,
    AssignmentCreate,
    AssignmentObject,
    AssignmentOut,
    AssignmentPatch,
)
from app.modules.objects.service import get_object_in_scope, territory_today
from app.modules.signals.notifications import add_notifications, users_covering_territory
from app.schemas import Page

router = APIRouter(tags=["assignments"])

ASSIGNEE_ROLES = (Role.admin, Role.mio_officer)

_author = aliased(AppUser)
_assignee = aliased(AppUser)
# Today in the time zone of the object's territory, like the deadlines of signal cards.
_local_today = func.timezone(Territory.timezone, func.now()).cast(Date)
_is_overdue = and_(Assignment.status == AssignmentStatus.open, Assignment.due_date < _local_today)

type Row = tuple[Assignment, ConstructionObject, str, str, str]


def _select_rows() -> Select[Assignment, ConstructionObject, str, str, str]:
    return (
        select(Assignment, ConstructionObject, Territory.timezone, _author.full_name, _assignee.full_name)
        .join(ConstructionObject, ConstructionObject.id == Assignment.object_id)
        .join(Territory, Territory.id == ConstructionObject.territory_id)
        .join(_author, _author.id == Assignment.author_id)
        .join(_assignee, _assignee.id == Assignment.assignee_id)
    )


def _to_out(row: Row) -> AssignmentOut:
    assignment, obj, timezone, author_name, assignee_name = row
    today = datetime.now(UTC).astimezone(ZoneInfo(timezone)).date()
    days_overdue = (today - assignment.due_date).days if assignment.status is AssignmentStatus.open else 0
    return AssignmentOut(
        id=assignment.id,
        object=AssignmentObject.model_validate(obj),
        author_id=assignment.author_id,
        author_name=author_name,
        assignee_id=assignment.assignee_id,
        assignee_name=assignee_name,
        task=assignment.task,
        due_date=assignment.due_date,
        status=assignment.status,
        is_overdue=days_overdue > 0,
        days_overdue=max(days_overdue, 0),
        result=assignment.result,
        completed_at=assignment.completed_at,
        created_at=assignment.created_at,
    )


def _load_out(session: Session, assignment_id: int) -> AssignmentOut:
    return _to_out(session.execute(_select_rows().where(Assignment.id == assignment_id)).one())


def _eligible_assignee(session: Session, assignee_id: int, territory_id: int) -> AppUser:
    for user in users_covering_territory(session, territory_id, ASSIGNEE_ROLES):
        if user.id == assignee_id:
            return user
    raise api_error(422, "invalid_assignee", "Этого сотрудника нельзя назначить исполнителем по данному объекту")


def _check_due_date(session: Session, territory_id: int, due_date: date) -> None:
    if due_date < territory_today(session, territory_id):
        raise api_error(422, "due_date_in_past", "Срок не может быть в прошлом")


def _notify(session: Session, assignee: AppUser, assignment: Assignment, object_name: str) -> None:
    add_notifications(
        session,
        [assignee],
        NotificationKind.assignment_new,
        "construction_object",
        assignment.object_id,
        {"assignment_id": assignment.id, "object_name": object_name, "due_date": assignment.due_date.isoformat()},
    )


@router.get("/assignments/assignees", response_model=list[AssigneeOut])
def list_assignees(
    session: SessionDep, user: StaffUser, scope: ScopeDep, object_id: Annotated[int, Query()]
) -> list[AppUser]:
    obj = get_object_in_scope(session, scope, object_id)
    return sorted(users_covering_territory(session, obj.territory_id, ASSIGNEE_ROLES), key=lambda u: u.full_name)


@router.post("/objects/{object_id}/assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(
    object_id: int, body: AssignmentCreate, session: SessionDep, user: StaffUser, scope: ScopeDep, request: Request
) -> AssignmentOut:
    obj = get_object_in_scope(session, scope, object_id)
    assignee = _eligible_assignee(session, body.assignee_id, obj.territory_id)
    _check_due_date(session, obj.territory_id, body.due_date)
    assignment = Assignment(
        object_id=obj.id, author_id=user.id, assignee_id=assignee.id, task=body.task, due_date=body.due_date
    )
    session.add(assignment)
    session.flush()
    session.refresh(assignment)
    audit.record(
        session, user, "assignment.create", "assignment", assignment.id, None, audit.snapshot(assignment), request
    )
    _notify(session, assignee, assignment, obj.name)
    session.commit()
    return _load_out(session, assignment.id)


@router.get("/objects/{object_id}/assignments", response_model=list[AssignmentOut])
def list_object_assignments(
    object_id: int, session: SessionDep, user: StaffUser, scope: ScopeDep
) -> list[AssignmentOut]:
    obj = get_object_in_scope(session, scope, object_id)
    rows = session.execute(
        _select_rows()
        .where(Assignment.object_id == obj.id)
        .order_by(Assignment.created_at.desc(), Assignment.id.desc())
    ).all()
    return [_to_out(row._tuple()) for row in rows]


@router.get("/assignments", response_model=Page[AssignmentOut])
def list_assignments(
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    page: PageDep,
    mine: Annotated[bool, Query()] = False,
    status: Annotated[AssignmentStatus | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
) -> Page[AssignmentOut]:
    stmt = _select_rows()
    if mine:
        stmt = stmt.where(Assignment.assignee_id == user.id)
    else:
        stmt = scope.restrict(stmt, ConstructionObject.territory_id)
    if status is not None:
        stmt = stmt.where(Assignment.status == status)
    if overdue is True:
        stmt = stmt.where(_is_overdue)
    elif overdue is False:
        stmt = stmt.where(~_is_overdue)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.execute(
        stmt.order_by(_is_overdue.desc(), Assignment.due_date, Assignment.id).limit(page.limit).offset(page.offset)
    ).all()
    return Page(items=[_to_out(row._tuple()) for row in rows], total=total)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: int,
    body: AssignmentPatch,
    session: SessionDep,
    user: StaffUser,
    scope: ScopeDep,
    request: Request,
) -> AssignmentOut:
    assignment = session.get(Assignment, assignment_id)
    obj = session.get(ConstructionObject, assignment.object_id) if assignment else None
    if assignment is None or obj is None:
        raise api_error(404, "assignment_not_found", "Поручение не найдено")
    in_scope = scope.contains(obj.territory_id)
    is_assignee = user.id == assignment.assignee_id
    is_author = user.id == assignment.author_id
    if not (in_scope or is_assignee or is_author):
        raise api_error(404, "assignment_not_found", "Поручение не найдено")
    is_manager = is_author or (user.role is Role.admin and in_scope)
    edits_fields = body.task is not None or body.due_date is not None or body.assignee_id is not None
    if (edits_fields or body.status == "cancelled") and not is_manager:
        raise forbidden("Изменить или отменить поручение может его автор или администратор")
    if body.status == "done" and not (is_assignee or is_manager):
        raise forbidden("Отметить выполнение может исполнитель, автор поручения или администратор")
    if assignment.status is not AssignmentStatus.open:
        raise api_error(409, "assignment_closed", "Поручение уже закрыто")

    before = audit.snapshot(assignment)
    new_assignee: AppUser | None = None
    if body.assignee_id is not None and body.assignee_id != assignment.assignee_id:
        new_assignee = _eligible_assignee(session, body.assignee_id, obj.territory_id)
        assignment.assignee_id = new_assignee.id
    if body.due_date is not None:
        if body.due_date != assignment.due_date:
            _check_due_date(session, obj.territory_id, body.due_date)
        assignment.due_date = body.due_date
    if body.task is not None:
        assignment.task = body.task
    if body.status == "done":
        assignment.status = AssignmentStatus.done
        assignment.result = body.result
        assignment.completed_at = datetime.now(UTC)
    elif body.status == "cancelled":
        assignment.status = AssignmentStatus.cancelled
    session.flush()
    session.refresh(assignment)
    audit.record(
        session, user, "assignment.update", "assignment", assignment.id, before, audit.snapshot(assignment), request
    )
    if new_assignee is not None:
        _notify(session, new_assignee, assignment, obj.name)
    session.commit()
    return _load_out(session, assignment.id)

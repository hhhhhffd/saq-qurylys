import re
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.deps import CurrentUser, ScopeDep, SessionDep
from app.errors import api_error
from app.models import ConstructionObject, Developer, SignalCard
from app.models.enums import Role, SignalStatus, Zone
from app.modules.developers.service import visible_developers
from app.modules.objects.service import _escape_like, object_rows_stmt
from app.modules.signals.service import card_stmt

router = APIRouter(prefix="/search", tags=["search"])

GROUP_LIMIT = 8
BIN_PATTERN = re.compile(r"[0-9]{12}")
STAFF_ROLES = (Role.admin, Role.mio_officer)


class ObjectHit(BaseModel):
    id: int
    name: str
    code: str
    address: str | None
    zone: Zone | None
    developer_name: str | None
    match: str


class DeveloperHit(BaseModel):
    id: int
    name: str
    bin: str
    object_id: int | None


class SignalHit(BaseModel):
    id: int
    number: str
    object_name: str
    status: SignalStatus


class SearchResult(BaseModel):
    objects: list[ObjectHit]
    developers: list[DeveloperHit]
    signals: list[SignalHit]


def _matched_field(obj: ConstructionObject, developer_name: str | None, needle: str) -> str:
    """Which attribute of the object contains the query, so the UI can show why it was found."""
    candidates = (
        ("name", obj.name),
        ("code", obj.code),
        ("address", obj.address),
        ("cadastral_number", obj.cadastral_number),
        ("alias", " ".join(obj.aliases)),
        ("developer", developer_name),
    )
    return next((field for field, value in candidates if value and needle in value.lower()), "developer_bin")


@router.get("", response_model=SearchResult)
def search(
    session: SessionDep,
    user: CurrentUser,
    scope: ScopeDep,
    q: Annotated[str, Query(min_length=2, max_length=200)],
) -> SearchResult:
    """One box for the header: objects and developers (staff only) and the signal cards the user may see."""
    needle = q.strip()
    if len(needle) < 2:
        raise api_error(422, "query_too_short", "Введите не менее 2 символов")
    objects: list[ObjectHit] = []
    developers: list[DeveloperHit] = []
    if user.role in STAFF_ROLES:
        stmt = object_rows_stmt(scope, q=needle).order_by(ConstructionObject.name, ConstructionObject.id)
        objects = [
            ObjectHit(
                id=obj.id,
                name=obj.name,
                code=obj.code,
                address=obj.address,
                zone=obj.zone,
                developer_name=developer_name,
                match=_matched_field(obj, developer_name, needle.lower()),
            )
            for obj, developer_name, _district in session.execute(stmt.limit(GROUP_LIMIT))
        ]

        developer_stmt = select(Developer)
        if BIN_PATTERN.fullmatch(needle):
            developer_stmt = developer_stmt.where(Developer.bin == needle)
        else:
            pattern = f"%{_escape_like(needle.lower())}%"
            developer_stmt = developer_stmt.where(
                visible_developers(scope),
                func.lower(Developer.name).like(pattern, escape="\\") | Developer.bin.like(pattern, escape="\\"),
            )
        in_scope_object = scope.restrict(
            select(func.min(ConstructionObject.id))
            .where(ConstructionObject.developer_id == Developer.id)
            .correlate(Developer),
            ConstructionObject.territory_id,
        ).scalar_subquery()
        developers = [
            DeveloperHit(id=developer.id, name=developer.name, bin=developer.bin, object_id=object_id)
            for developer, object_id in session.execute(
                developer_stmt.add_columns(in_scope_object).order_by(Developer.name, Developer.id).limit(GROUP_LIMIT)
            )
        ]

    cards = card_stmt(user, scope).where(SignalCard.number.ilike(f"%{_escape_like(needle)}%"))
    signals = [
        SignalHit(id=card.id, number=card.number, object_name=object_name, status=card.status)
        for card, object_name, *_ in session.execute(cards.order_by(SignalCard.number.desc()).limit(GROUP_LIMIT))
    ]
    return SearchResult(objects=objects, developers=developers, signals=signals)

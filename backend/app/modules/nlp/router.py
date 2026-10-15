from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import audit
from app.deps import GlobalAdmin, PageDep, SessionDep, StaffUser
from app.errors import api_error
from app.models import Phrase
from app.models.enums import PhraseCategory
from app.modules.nlp.schemas import PhraseCreate, PhraseOut, PhraseUpdate
from app.schemas import Page

router = APIRouter(prefix="/phrases", tags=["phrases"])


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ensure_unique(session: SessionDep, category: PhraseCategory, text: str, own_id: int | None = None) -> None:
    stmt = select(Phrase.id).where(Phrase.category == category, func.lower(Phrase.text) == text.lower())
    if own_id is not None:
        stmt = stmt.where(Phrase.id != own_id)
    if session.scalar(stmt) is not None:
        raise api_error(409, "phrase_exists", "Такая формулировка уже есть в словаре")


@router.get("", response_model=Page[PhraseOut])
def list_phrases(
    session: SessionDep,
    user: StaffUser,
    page: PageDep,
    category: Annotated[PhraseCategory | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[PhraseOut]:
    stmt = select(Phrase)
    if category is not None:
        stmt = stmt.where(Phrase.category == category)
    if is_active is not None:
        stmt = stmt.where(Phrase.is_active == is_active)
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(Phrase.text.ilike(pattern) | func.array_to_string(Phrase.variants, " ").ilike(pattern))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(Phrase.category, Phrase.id).limit(page.limit).offset(page.offset))
    return Page(items=[PhraseOut.model_validate(row) for row in rows], total=total)


@router.post("", response_model=PhraseOut, status_code=201)
def create_phrase(body: PhraseCreate, session: SessionDep, admin: GlobalAdmin, request: Request) -> Phrase:
    _ensure_unique(session, body.category, body.text)
    phrase = Phrase(**body.model_dump())
    session.add(phrase)
    session.flush()
    audit.record(session, admin, "phrase.create", "phrase", phrase.id, None, audit.snapshot(phrase), request)
    session.commit()
    return phrase


@router.patch("/{phrase_id}", response_model=PhraseOut)
def update_phrase(
    phrase_id: int, body: PhraseUpdate, session: SessionDep, admin: GlobalAdmin, request: Request
) -> Phrase:
    phrase = session.get(Phrase, phrase_id)
    if phrase is None:
        raise api_error(404, "phrase_not_found", "Формулировка не найдена")
    changes = body.model_dump(exclude_unset=True)
    _ensure_unique(session, changes.get("category", phrase.category), changes.get("text", phrase.text), phrase.id)
    before = audit.snapshot(phrase)
    for field, value in changes.items():
        setattr(phrase, field, value)
    session.flush()
    audit.record(session, admin, "phrase.update", "phrase", phrase.id, before, audit.snapshot(phrase), request)
    session.commit()
    return phrase

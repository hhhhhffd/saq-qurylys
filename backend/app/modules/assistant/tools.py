"""Tools of the assistant: read-only queries over the data the user may see (docs/ASSISTANT.md).

Every executor takes (session, user, scope, args) and returns a small JSON-serialisable dict. They repeat the
rights of the HTTP API: the registry, publications and the summary are for staff, cards follow `card_stmt`, and
the territory scope is always applied. An object or card out of scope is reported as `not_found`."""

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdPost, AppUser, ConstructionObject, SignalCard
from app.models.enums import AdStatus, Role, SignalStatus, Zone
from app.modules.assistant import knowledge
from app.modules.nlp.text import strip_ocr_marker
from app.modules.objects.router import build_detail
from app.modules.objects.service import get_object_in_scope, object_rows_stmt
from app.modules.signals import service as signals_service
from app.modules.signals.labels import RU as SIGNAL_LABELS
from app.scope import TerritoryScope

STAFF_ROLES = frozenset({Role.admin, Role.mio_officer})
MAX_ITEMS = 10
MAX_TEXT_CHARS = 300
MAX_GUIDE_CHARS = 800
MAX_QUERY_CHARS = 200

Args = dict[str, Any]
Executor = Callable[[Session, AppUser, TerritoryScope, Args], dict[str, Any]]


class ToolArgError(Exception):
    """The model passed arguments that do not fit the schema; the message goes back to the model."""


class NotFound(Exception):
    pass


def _clip(value: str | None, limit: int = MAX_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _text(args: Args, name: str, *, required: bool = False) -> str | None:
    value = args.get(name)
    if value is None or value == "":
        if required:
            raise ToolArgError(f"Параметр {name} обязателен")
        return None
    if not isinstance(value, str):
        raise ToolArgError(f"Параметр {name} должен быть строкой")
    return value.strip()[:MAX_QUERY_CHARS]


def _id(args: Args, name: str, *, required: bool = False) -> int | None:
    value = args.get(name)
    if value is None:
        if required:
            raise ToolArgError(f"Параметр {name} обязателен")
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolArgError(f"Параметр {name} должен быть целым числом")
    return value


def _enum[E: (Zone, SignalStatus, AdStatus)](args: Args, name: str, enum: type[E]) -> E | None:
    value = _text(args, name)
    if value is None:
        return None
    try:
        return enum(value)
    except ValueError:
        allowed = ", ".join(item.value for item in enum)
        raise ToolArgError(f"Параметр {name}: допустимы {allowed}") from None


_SCORE_RANGE = re.compile(r"score_(\d+)_(\d+)")
_SCORE_WITHOUT_R1_R2 = re.compile(r"score_(\d+)_without_r1_r2")


def _zone_reason(code: str) -> str:
    """Words for a code of `risk.engine.decide_zone`: the model would otherwise repeat the raw code."""
    if code == "r1_and_r2":
        return "Порог красной зоны достигнут, сработали R1 и R2"
    if match := _SCORE_WITHOUT_R1_R2.fullmatch(code):
        return f"Балл {match[1]}+, но R1 и R2 вместе не сработали: красной зоны нет"
    if match := _SCORE_RANGE.fullmatch(code):
        return f"Балл в диапазоне {match[1]}–{match[2]}"
    return code


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ---------------------------------------------------------------- executors


def search_guide(session: Session, user: AppUser, scope: TerritoryScope, args: Args) -> dict[str, Any]:
    query = _text(args, "query", required=True) or ""
    return {
        "sections": [
            {"title": chunk.title, "page": chunk.page, "text": _clip(chunk.text, MAX_GUIDE_CHARS)}
            for chunk in knowledge.search(query, 4)
        ]
    }


def search_objects(session: Session, user: AppUser, scope: TerritoryScope, args: Args) -> dict[str, Any]:
    query = _text(args, "query")
    zone = _enum(args, "zone", Zone)
    stmt = object_rows_stmt(scope, zone=zone, q=query)
    rows = session.execute(
        stmt.order_by(ConstructionObject.score.desc().nulls_last(), ConstructionObject.id).limit(MAX_ITEMS)
    )
    return {
        "objects": [
            {
                "id": obj.id,
                "code": obj.code,
                "name": obj.name,
                "developer": developer,
                "district": district,
                "score": obj.score,
                "zone": obj.zone,
                "key_status": obj.key_status,
                "url": f"/objects/{obj.id}",
            }
            for obj, developer, district in rows
        ]
    }


def get_object(session: Session, user: AppUser, scope: TerritoryScope, args: Args) -> dict[str, Any]:
    object_id = _id(args, "object_id", required=True)
    assert object_id is not None
    try:
        obj = get_object_in_scope(session, scope, object_id)
    except HTTPException:
        raise NotFound from None
    detail = build_detail(session, obj)
    result: dict[str, Any] = {
        "id": obj.id,
        "code": obj.code,
        "name": obj.name,
        "address": obj.address,
        "developer": detail.developer.name if detail.developer else None,
        "district": detail.district_name,
        "construction_status": obj.construction_status,
        "planned_completion": obj.planned_completion,
        "forecast_completion": obj.forecast_completion,
        "readiness_actual_pct": obj.readiness_actual_pct,
        "readiness_claimed_pct": obj.readiness_claimed_pct,
        "score": obj.score,
        "zone": obj.zone,
        "key_status": obj.key_status,
        "key_status_detail": detail.key_status_detail,
        "ads_7d_count": detail.ads_7d_count,
        "documents": len(detail.documents),
        "inspections": len(detail.inspections),
        "complaints": len(detail.complaints),
        "url": f"/objects/{obj.id}",
    }
    if detail.latest_score is not None:
        factors, needs_check, legal_basis = signals_service.breakdown_parts(detail.latest_score.breakdown)
        result["zone_reasons"] = [_zone_reason(code) for code in detail.latest_score.zone_reasons]
        result["risk_factors"] = [
            {"label": factor["label"], "weight": factor["weight"]} for factor in factors if factor["triggered"]
        ]
        flags = SIGNAL_LABELS["needs_check_flag"]
        result["needs_check"] = [flags.get(item["code"], item["code"]) for item in needs_check]
        result["legal_basis_status"] = legal_basis
        result["scored_at"] = detail.latest_score.calculated_at
    return result


def list_signals(session: Session, user: AppUser, scope: TerritoryScope, args: Args) -> dict[str, Any]:
    status = _enum(args, "status", SignalStatus)
    object_id = _id(args, "object_id")
    stmt = signals_service.card_stmt(user, scope)
    if status is not None:
        stmt = stmt.where(SignalCard.status == status)
    if object_id is not None:
        stmt = stmt.where(SignalCard.object_id == object_id)
    rows = session.execute(stmt.order_by(SignalCard.created_at.desc(), SignalCard.id.desc()).limit(MAX_ITEMS))
    items = []
    for card, name, zone, timezone, is_demo in rows:
        row = signals_service.to_row(
            signals_service.CardView(card=card, object_name=name, zone=zone, timezone=timezone, is_demo=is_demo)
        )
        items.append(
            {
                "id": row.id,
                "number": row.number,
                "object": {"id": row.object_id, "name": row.object_name},
                "status": row.status,
                "recipient": row.recipient,
                "due_date": row.due_date,
                "is_overdue": row.is_overdue,
                "url": f"/signals/{row.id}",
            }
        )
    return {"signals": items}


def search_ads(session: Session, user: AppUser, scope: TerritoryScope, args: Args) -> dict[str, Any]:
    query = _text(args, "query")
    object_id = _id(args, "object_id")
    status = _enum(args, "status", AdStatus)
    stmt = select(AdPost, ConstructionObject.name).outerjoin(
        ConstructionObject, ConstructionObject.id == AdPost.object_id
    )
    stmt = scope.restrict(stmt, AdPost.territory_id)
    if object_id is not None:
        stmt = stmt.where(AdPost.object_id == object_id)
    if status is not None:
        stmt = stmt.where(AdPost.status == status)
    if query:
        pattern = _like(query)
        stmt = stmt.where(AdPost.text.ilike(pattern) | ConstructionObject.name.ilike(pattern))
    recency = func.coalesce(AdPost.published_at, AdPost.captured_at, AdPost.created_at)
    rows = session.execute(
        stmt.order_by(AdPost.max_phrase_weight.desc(), recency.desc(), AdPost.id.desc()).limit(MAX_ITEMS)
    )
    return {
        "ads": [
            {
                "id": ad.id,
                "platform": ad.platform,
                "date": ad.published_at or ad.captured_at or ad.created_at,
                "object": {"id": ad.object_id, "name": object_name} if ad.object_id is not None else None,
                "payment_schemes": ad.payment_schemes,
                "status": ad.status,
                "text": _clip(strip_ocr_marker(ad.text or "")),
                "url": f"/ads?ad={ad.id}",
            }
            for ad, object_name in rows
        ]
    }


def work_summary(session: Session, user: AppUser, scope: TerritoryScope, args: Args) -> dict[str, Any]:
    zones = session.execute(
        scope.restrict(select(ConstructionObject.zone, func.count()), ConstructionObject.territory_id).group_by(
            ConstructionObject.zone
        )
    )
    zone_counts = Counter(dict(zones.tuples().all()))
    cards = session.execute(
        signals_service.card_stmt(user, scope)
        .with_only_columns(SignalCard.status, func.count())
        .group_by(SignalCard.status)
    )
    card_counts = dict(cards.tuples().all())
    return {
        "zones": {
            "green": zone_counts[Zone.green],
            "yellow": zone_counts[Zone.yellow],
            "red": zone_counts[Zone.red],
            "unscored": zone_counts[None],
            "total": sum(zone_counts.values()),
        },
        "signals": {status.value: card_counts.get(status, 0) for status in SignalStatus},
    }


# ---------------------------------------------------------------- registry


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict[str, Any]
    required: tuple[str, ...]
    staff_only: bool
    run: Executor
    # Shown to the user while the tool runs, per language of the answer; `{name}` is replaced by an argument.
    labels: dict[str, str]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": self.properties, "required": list(self.required)},
            },
        }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            "search_guide",
            "Поиск по руководству сотрудника SAQ: как выполнить действие, что значит термин. Используй, если "
            "найденных выше разделов не хватает.",
            {"query": _string("Поисковый запрос своими словами")},
            ("query",),
            False,
            search_guide,
            {"ru": "Ищу в руководстве: {query}", "kk": "Нұсқаулықтан іздеймін: {query}"},
        ),
        Tool(
            "search_objects",
            "Поиск объектов строительства в реестре по названию, коду, адресу, кадастровому номеру или "
            "застройщику. Без query — все объекты (например, все объекты красной зоны с zone=red). "
            "Возвращает до 10 объектов, самые опасные первыми.",
            {
                "query": _string("Часть названия, кода, адреса или имени застройщика"),
                "zone": {"type": "string", "enum": [zone.value for zone in Zone], "description": "Фильтр по зоне"},
            },
            (),
            True,
            search_objects,
            {"ru": "Ищу объекты: {query}", "kk": "Нысандарды іздеймін: {query}"},
        ),
        Tool(
            "get_object",
            "Карточка объекта: паспорт, балл риска, зона, причины зоны, сработавшие факторы, что нужно проверить.",
            {"object_id": _integer("Идентификатор объекта")},
            ("object_id",),
            True,
            get_object,
            {"ru": "Открываю объект №{object_id}", "kk": "№{object_id} нысанды ашамын"},
        ),
        Tool(
            "list_signals",
            "Сигнальные карточки, которые видит пользователь, новые первыми (до 10).",
            {
                "status": {
                    "type": "string",
                    "enum": [status.value for status in SignalStatus],
                    "description": "Фильтр по статусу",
                },
                "object_id": _integer("Только карточки этого объекта"),
            },
            (),
            False,
            list_signals,
            {"ru": "Смотрю сигнальные карточки", "kk": "Сигналдық карточкаларды қараймын"},
        ),
        Tool(
            "search_ads",
            "Публикации (объявления) о продаже жилья: поиск по тексту или названию объекта (до 10).",
            {
                "query": _string("Слово или фраза из текста объявления или название объекта"),
                "object_id": _integer("Только публикации, привязанные к этому объекту"),
                "status": {
                    "type": "string",
                    "enum": [status.value for status in AdStatus],
                    "description": "Фильтр по статусу публикации",
                },
            },
            (),
            True,
            search_ads,
            {"ru": "Ищу публикации: {query}", "kk": "Жарияланымдарды іздеймін: {query}"},
        ),
        Tool(
            "work_summary",
            "Сводка по территории пользователя: сколько объектов в каждой зоне и сколько сигнальных карточек "
            "в каждом статусе.",
            {},
            (),
            True,
            work_summary,
            {"ru": "Считаю сводку", "kk": "Жиынтықты есептеймін"},
        ),
    )
}


def available_tools(user: AppUser) -> list[Tool]:
    return [tool for tool in TOOLS.values() if not tool.staff_only or user.role in STAFF_ROLES]


def tool_schemas(user: AppUser) -> list[dict[str, Any]]:
    return [tool.schema() for tool in available_tools(user)]


def label(name: str, args: Args, language: str) -> str:
    """Human-readable description of a tool call for the `tool` event."""
    tool = TOOLS.get(name)
    if tool is None:
        return name
    values = defaultdict(str, {key: _clip(str(value), 60) or "" for key, value in args.items()})
    # A label whose only argument is absent ("Ищу объекты: ") loses the dangling colon.
    return tool.labels.get(language, tool.labels["ru"]).format_map(values).rstrip(": ")


def run_tool(name: str, args: object, session: Session, user: AppUser, scope: TerritoryScope) -> dict[str, Any]:
    """Executes a tool for the user. Never raises for a model mistake: the error text goes back to the model."""
    tool = TOOLS.get(name)
    if tool is None or tool not in available_tools(user):
        return {"error": f"Инструмент {name} недоступен"}
    if not isinstance(args, dict):
        return {"error": "Аргументы должны быть JSON-объектом"}
    try:
        return tool.run(session, user, scope, args)
    except ToolArgError as exc:
        return {"error": str(exc)}
    except NotFound:
        return {"error": "not_found"}

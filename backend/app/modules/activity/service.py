"""Live activity feed (SPEC 10.7): publications received, score changes and signal cards.

Events are not stored; they are read from the tables that already record them. Only the last `LOOKBACK`
is searched, so the query stays cheap however long the system has been running.
"""

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import SQLColumnExpression

from app.errors import api_error
from app.models import AdPost, ConstructionObject, RiskScore, SignalCard
from app.models.enums import ScoreTrigger, Zone
from app.modules.activity.schemas import ActivityEvent, ActivityFeed, ActivityKind
from app.scope import TerritoryScope

LOOKBACK = timedelta(days=7)
# What a client without a cursor gets: enough to show the feed is alive, few enough not to pile up animations.
INITIAL_LIMIT = 5

# Events of different kinds can share a timestamp; this order settles their sequence.
KIND_ORDER = (
    ActivityKind.ad_received,
    ActivityKind.score_changed,
    ActivityKind.signal_created,
    ActivityKind.signal_sent,
)


@dataclass(frozen=True, order=True)
class Position:
    """Place of an event in the feed. (time, kind, row id) is unique, so events with equal timestamps are
    neither repeated nor skipped between two polls."""

    at: datetime
    kind_rank: int
    row_id: int


Found = list[tuple[Position, ActivityEvent]]


def encode_cursor(position: Position) -> str:
    raw = f"{position.at.astimezone(UTC).isoformat()}|{position.kind_rank}|{position.row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> Position:
    try:
        at_text, rank_text, id_text = base64.urlsafe_b64decode(cursor).decode().split("|")
        position = Position(datetime.fromisoformat(at_text), int(rank_text), int(id_text))
    except ValueError as exc:  # also covers bad base64, non-UTF-8 bytes and a wrong number of parts
        raise api_error(400, "invalid_cursor", "Некорректный курсор ленты") from exc
    if position.at.tzinfo is None or not 0 <= position.kind_rank < len(KIND_ORDER):
        raise api_error(400, "invalid_cursor", "Некорректный курсор ленты")
    return position


def _page[*Ts](
    stmt: Select[*Ts],
    at: SQLColumnExpression[Any],
    row_id: SQLColumnExpression[Any],
    kind: ActivityKind,
    cutoff: datetime,
    after: Position | None,
    limit: int,
) -> Select[*Ts]:
    """Events of one kind inside the look-back and, with a cursor, strictly after it. Without a cursor the
    newest come first; with one the oldest do, so a burst larger than `limit` is delivered in several polls."""
    stmt = stmt.where(at >= cutoff)
    if after is None:
        return stmt.order_by(at.desc(), row_id.desc()).limit(limit)
    rank = KIND_ORDER.index(kind)
    stmt = stmt.where(tuple_(at, rank, row_id) > tuple_(after.at, after.kind_rank, after.row_id))
    return stmt.order_by(at, row_id).limit(limit)


def _ad_events(session: Session, scope: TerritoryScope, cutoff: datetime, after: Position | None, limit: int) -> Found:
    kind = ActivityKind.ad_received
    stmt = (
        select(
            AdPost.id,
            AdPost.created_at.label("at"),
            AdPost.origin,
            AdPost.platform,
            AdPost.is_demo,
            AdPost.object_id,
            ConstructionObject.name.label("object_name"),
        )
        .select_from(AdPost)
        .outerjoin(ConstructionObject, ConstructionObject.id == AdPost.object_id)
    )
    stmt = _page(scope.restrict(stmt, AdPost.territory_id), AdPost.created_at, AdPost.id, kind, cutoff, after, limit)
    return [
        (
            Position(row.at, KIND_ORDER.index(kind), row.id),
            ActivityEvent(
                id=f"{kind}:{row.id}",
                kind=kind,
                at=row.at,
                ad_id=row.id,
                object_id=row.object_id,
                object_name=row.object_name,
                origin=row.origin.value,
                platform=row.platform.value,
                is_demo=row.is_demo,
            ),
        )
        for row in session.execute(stmt)
    ]


def _score_events(
    session: Session, scope: TerritoryScope, cutoff: datetime, after: Position | None, limit: int
) -> Found:
    """A score row is an event when its score or zone differs from the object's previous row. Replayed history
    (SPEC 10.5) is neither an event nor a "previous" row. LAG runs over the whole history of the objects that
    were scored recently, so the first row inside the look-back still has its predecessor."""
    kind = ActivityKind.score_changed
    recent = (
        select(RiskScore.object_id)
        .join(ConstructionObject, ConstructionObject.id == RiskScore.object_id)
        .where(RiskScore.calculated_at >= cutoff, RiskScore.trigger != ScoreTrigger.replay)
    )
    # The scope is applied here: only objects of the user's territory enter the window computation.
    recent = scope.restrict(recent, ConstructionObject.territory_id)
    scores = (
        select(
            RiskScore.id,
            RiskScore.object_id,
            RiskScore.calculated_at.label("at"),
            RiskScore.score,
            RiskScore.zone,
            func.lag(RiskScore.score)
            .over(partition_by=RiskScore.object_id, order_by=(RiskScore.calculated_at, RiskScore.id))
            .label("score_before"),
            func.lag(RiskScore.zone)
            .over(partition_by=RiskScore.object_id, order_by=(RiskScore.calculated_at, RiskScore.id))
            .label("zone_before"),
        )
        .where(RiskScore.trigger != ScoreTrigger.replay, RiskScore.object_id.in_(recent))
        .subquery("scores")
    )
    stmt = (
        select(
            scores.c.id,
            scores.c.at,
            scores.c.object_id,
            ConstructionObject.name.label("object_name"),
            ConstructionObject.is_demo,
            scores.c.score,
            scores.c.score_before,
            scores.c.zone,
            scores.c.zone_before,
        )
        .select_from(scores)
        .join(ConstructionObject, ConstructionObject.id == scores.c.object_id)
        .where(
            scores.c.score_before.is_not(None),
            or_(scores.c.score != scores.c.score_before, scores.c.zone != scores.c.zone_before),
        )
    )
    stmt = _page(stmt, scores.c.at, scores.c.id, kind, cutoff, after, limit)
    return [
        (
            Position(row.at, KIND_ORDER.index(kind), row.id),
            ActivityEvent(
                id=f"{kind}:{row.id}",
                kind=kind,
                at=row.at,
                object_id=row.object_id,
                object_name=row.object_name,
                score_before=row.score_before,
                score_after=row.score,
                zone_before=Zone(row.zone_before),
                zone_after=Zone(row.zone),
                is_demo=row.is_demo,
            ),
        )
        for row in session.execute(stmt)
    ]


def _signal_events(
    session: Session, scope: TerritoryScope, kind: ActivityKind, cutoff: datetime, after: Position | None, limit: int
) -> Found:
    """`signal_created` is dated by the card's creation, `signal_sent` by `sent_at` (set only by confirm-and-send)."""
    at = SignalCard.created_at if kind is ActivityKind.signal_created else SignalCard.sent_at
    stmt = (
        select(
            SignalCard.id,
            at.label("at"),
            SignalCard.number,
            SignalCard.origin,
            SignalCard.object_id,
            ConstructionObject.name.label("object_name"),
            ConstructionObject.is_demo,
        )
        .select_from(SignalCard)
        .join(ConstructionObject, ConstructionObject.id == SignalCard.object_id)
    )
    stmt = _page(scope.restrict(stmt, ConstructionObject.territory_id), at, SignalCard.id, kind, cutoff, after, limit)
    return [
        (
            Position(row.at, KIND_ORDER.index(kind), row.id),
            ActivityEvent(
                id=f"{kind}:{row.id}",
                kind=kind,
                at=row.at,
                object_id=row.object_id,
                object_name=row.object_name,
                signal_id=row.id,
                origin=row.origin.value,
                number=row.number,
                is_demo=row.is_demo,
            ),
        )
        for row in session.execute(stmt)
    ]


def load_feed(session: Session, scope: TerritoryScope, after: str | None, limit: int) -> ActivityFeed:
    """Without a cursor: the latest `INITIAL_LIMIT` events. With one: the oldest `limit` events after it.
    Items are newest first either way and `cursor` points at the newest of them."""
    cutoff = datetime.now(UTC) - LOOKBACK
    position = decode_cursor(after) if after is not None else None
    size = INITIAL_LIMIT if position is None else limit
    found: Found = [
        *_ad_events(session, scope, cutoff, position, size),
        *_score_events(session, scope, cutoff, position, size),
        *(
            event
            for kind in (ActivityKind.signal_created, ActivityKind.signal_sent)
            for event in _signal_events(session, scope, kind, cutoff, position, size)
        ),
    ]
    # Every kind returned its own best `size`, so the best `size` overall are among them.
    found.sort(key=lambda item: item[0], reverse=position is None)
    page = found[:size]
    if not page:
        # Nothing yet: a later event is newer than the start of the look-back, whatever its time.
        return ActivityFeed(items=[], cursor=after or encode_cursor(Position(cutoff, 0, 0)))
    if position is not None:
        page.reverse()
    return ActivityFeed(items=[event for _, event in page], cursor=encode_cursor(page[0][0]))

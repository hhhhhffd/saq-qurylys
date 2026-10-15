"""Live activity feed (SPEC 10.7): publications received, score changes and signal cards.

Events are not stored; they are read from the tables that already record them. Only the last `LOOKBACK`
is searched, so the query stays cheap however long the system has been running.

A row is dated by the start of the transaction that wrote it, which can be well before it becomes visible to
the feed. So a poll also looks `GRACE` back from the cursor and sends again what it finds there; the client
tells the events it has seen by their ids.
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
# How far before the cursor a poll looks for events that were committed after the cursor moved past their time,
# and how many of them (the oldest first) each kind sends per poll.
GRACE = timedelta(minutes=2)
GRACE_LIMIT = 50
# A cursor issued longer ago than this belongs to a client that was away: it gets the latest events and `reset`
# instead of the whole backlog.
RESET_AFTER = timedelta(minutes=10)

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


def encode_cursor(position: Position, issued_at: datetime) -> str:
    """The newest event the client has, and when the cursor was handed out (to tell a client that was away)."""
    at, issued = position.at.astimezone(UTC), issued_at.astimezone(UTC)
    raw = f"{at.isoformat()}|{position.kind_rank}|{position.row_id}|{issued.isoformat()}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[Position, datetime]:
    try:
        at_text, rank_text, id_text, issued_text = base64.urlsafe_b64decode(cursor).decode().split("|")
        position = Position(datetime.fromisoformat(at_text), int(rank_text), int(id_text))
        issued_at = datetime.fromisoformat(issued_text)
    except ValueError as exc:  # also covers bad base64, non-UTF-8 bytes and a wrong number of parts
        raise api_error(400, "invalid_cursor", "Некорректный курсор ленты") from exc
    if position.at.tzinfo is None or issued_at.tzinfo is None or not 0 <= position.kind_rank < len(KIND_ORDER):
        raise api_error(400, "invalid_cursor", "Некорректный курсор ленты")
    return position, issued_at


def _page[*Ts](
    stmt: Select[*Ts],
    at: SQLColumnExpression[Any],
    row_id: SQLColumnExpression[Any],
    kind: ActivityKind,
    cutoff: datetime,
    after: Position | None,
    limit: int,
) -> Select[*Ts]:
    """Events of one kind inside the look-back. Without a cursor the newest come first.

    With a cursor, the events after it come first, the oldest first, so a burst larger than `limit` is delivered
    in several polls; they are followed by up to `GRACE_LIMIT` events from the grace window that are not after
    the cursor (`load_feed` tells the two apart by position).
    """
    stmt = stmt.where(at >= cutoff)
    if after is None:
        return stmt.order_by(at.desc(), row_id.desc()).limit(limit)
    rank = KIND_ORDER.index(kind)
    ahead = tuple_(at, rank, row_id) > tuple_(after.at, after.kind_rank, after.row_id)
    return stmt.where(at >= after.at - GRACE).order_by(ahead.desc(), at, row_id).limit(limit + GRACE_LIMIT)


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
    """Without a cursor, or with one issued more than `RESET_AFTER` ago (`reset`): the latest `INITIAL_LIMIT`
    events. With a current one: the oldest `limit` events after it, and the events of the grace window before it.
    Items are newest first either way. `cursor` points at the newest event the client is given, and never moves
    back."""
    now = datetime.now(UTC)
    cutoff = now - LOOKBACK
    position: Position | None = None
    reset = False
    if after is not None:
        position, issued_at = decode_cursor(after)
        reset = now - issued_at > RESET_AFTER
        if reset:
            position = None
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
    if position is None:
        # Every kind returned its own newest `size`, so the newest `size` overall are among them.
        page = sorted(found, key=lambda item: item[0], reverse=True)[:size]
        # Nothing yet: a later event is newer than the start of the look-back, whatever its time.
        newest = page[0][0] if page else Position(cutoff, 0, 0)
    else:
        # Every kind returned its own oldest events after the cursor, so the oldest `size` overall are among them.
        ahead = sorted((item for item in found if item[0] > position), key=lambda item: item[0])[:size]
        page = sorted(
            [*ahead, *(item for item in found if item[0] <= position)], key=lambda item: item[0], reverse=True
        )
        newest = ahead[-1][0] if ahead else position
    return ActivityFeed(items=[event for _, event in page], cursor=encode_cursor(newest, now), reset=reset)

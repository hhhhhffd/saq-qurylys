from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.models.enums import Zone


class ActivityKind(StrEnum):
    ad_received = "ad_received"
    score_changed = "score_changed"
    signal_created = "signal_created"
    signal_sent = "signal_sent"


class ActivityEvent(BaseModel):
    """One entry of the live feed. Only the fields of its `kind` are filled; `id` is "<kind>:<row id>".

    `origin` is the publication origin (manual/capture/collector/citizen) for `ad_received` and the card
    origin (auto/manual) for the signal kinds.
    """

    id: str
    kind: ActivityKind
    at: datetime
    object_id: int | None = None
    object_name: str | None = None
    ad_id: int | None = None
    signal_id: int | None = None
    origin: str | None = None
    platform: str | None = None
    score_before: int | None = None
    score_after: int | None = None
    zone_before: Zone | None = None
    zone_after: Zone | None = None
    number: str | None = None
    is_demo: bool | None = None


class ActivityFeed(BaseModel):
    """`items` are newest first. Pass `cursor` back as `after` to get what happened since.

    A poll may send events the client already has (it looks back 2 minutes from the cursor): tell them by
    `ActivityEvent.id`. `reset` means the cursor was too old (the client was away): `items` are only the latest
    events, not everything since, and are not news.
    """

    items: list[ActivityEvent]
    cursor: str
    reset: bool = False

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.models.enums import Zone
from app.modules.objects.schemas import ObjectRow


class DashboardCounts(BaseModel):
    green: int
    yellow: int
    red: int
    unscored: int
    total: int


class Dashboard(BaseModel):
    counts: DashboardCounts
    last_updated_at: datetime | None
    objects: list[ObjectRow]


class TimelineStep(StrEnum):
    week = "week"
    day = "day"


class TimelineObjectZone(BaseModel):
    object_id: int
    score: int
    zone: Zone


class TimelineFrame(BaseModel):
    at: datetime
    # Objects that had no score yet at this moment are left out.
    objects: list[TimelineObjectZone]


class TimelineObject(BaseModel):
    object_id: int
    name: str
    lat: float | None
    lon: float | None
    is_demo: bool


class Timeline(BaseModel):
    frames: list[TimelineFrame]
    # Every object that has a score in at least one frame.
    objects: list[TimelineObject]

"""Working-day arithmetic for the Kazakhstan production calendar.

Saturdays and Sundays are days off. The `holiday` table overrides that: a `holiday` row makes
any day a day off, a `workday` row makes a weekend day a (transferred) working day.
"""

from collections.abc import Mapping
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Holiday
from app.models.enums import HolidayKind

SATURDAY = 5


def is_working_day(day: date, overrides: Mapping[date, HolidayKind]) -> bool:
    kind = overrides.get(day)
    if kind is HolidayKind.holiday:
        return False
    if kind is HolidayKind.workday:
        return True
    return day.weekday() < SATURDAY


def shift_working_days(start: date, days: int, overrides: Mapping[date, HolidayKind]) -> date:
    """Move `days` working days forward (negative: backward). The start day itself is not counted,
    so shift(Friday, 1) is Monday and shift(x, 0) is x."""
    step = 1 if days >= 0 else -1
    current = start
    remaining = abs(days)
    while remaining:
        current += timedelta(days=step)
        if is_working_day(current, overrides):
            remaining -= 1
    return current


def load_overrides(session: Session) -> dict[date, HolidayKind]:
    # The table holds a few dozen rows per year, so reading all of it is simpler than windowing.
    return {row.day: row.kind for row in session.scalars(select(Holiday))}


def add_working_days(session: Session, start: date, days: int) -> date:
    return shift_working_days(start, days, load_overrides(session))

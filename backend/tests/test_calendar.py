from datetime import date

from sqlalchemy.orm import Session

from app.calendar import add_working_days, is_working_day, shift_working_days
from app.models import Holiday
from app.models.enums import HolidayKind

MONDAY = date(2026, 10, 12)
FRIDAY = date(2026, 10, 16)
NO_OVERRIDES: dict[date, HolidayKind] = {}


def test_weekends_are_days_off() -> None:
    assert is_working_day(FRIDAY, NO_OVERRIDES)
    assert not is_working_day(date(2026, 10, 17), NO_OVERRIDES)  # Saturday
    assert not is_working_day(date(2026, 10, 18), NO_OVERRIDES)  # Sunday


def test_zero_days_returns_start_even_on_a_weekend() -> None:
    assert shift_working_days(date(2026, 10, 17), 0, NO_OVERRIDES) == date(2026, 10, 17)


def test_friday_plus_one_is_monday() -> None:
    assert shift_working_days(FRIDAY, 1, NO_OVERRIDES) == date(2026, 10, 19)


def test_five_working_days_without_holidays() -> None:
    assert shift_working_days(MONDAY, 5, NO_OVERRIDES) == date(2026, 10, 19)


def test_holiday_on_a_weekday_is_skipped() -> None:
    overrides = {date(2026, 10, 14): HolidayKind.holiday}
    assert shift_working_days(MONDAY, 5, overrides) == date(2026, 10, 20)


def test_transferred_workday_on_saturday_counts() -> None:
    overrides = {date(2026, 10, 14): HolidayKind.holiday, date(2026, 10, 17): HolidayKind.workday}
    assert is_working_day(date(2026, 10, 17), overrides)
    assert shift_working_days(MONDAY, 5, overrides) == date(2026, 10, 19)
    assert shift_working_days(MONDAY, 4, overrides) == date(2026, 10, 17)


def test_holiday_on_weekend_changes_nothing() -> None:
    overrides = {date(2026, 10, 17): HolidayKind.holiday}
    assert shift_working_days(FRIDAY, 1, overrides) == date(2026, 10, 19)


def test_long_holiday_block_across_a_weekend() -> None:
    overrides = {date(2026, 10, day): HolidayKind.holiday for day in (19, 20, 21)}
    assert shift_working_days(FRIDAY, 1, overrides) == date(2026, 10, 22)


def test_negative_shift_goes_back_over_weekends_and_holidays() -> None:
    overrides = {FRIDAY: HolidayKind.holiday}
    assert shift_working_days(date(2026, 10, 19), -1, NO_OVERRIDES) == FRIDAY
    assert shift_working_days(date(2026, 10, 19), -1, overrides) == date(2026, 10, 15)


def test_add_working_days_reads_holidays_from_database(db: Session) -> None:
    db.add_all(
        [
            Holiday(day=date(2026, 10, 14), kind=HolidayKind.holiday, name="Тестовый праздник"),
            Holiday(day=date(2026, 10, 17), kind=HolidayKind.workday, name="Перенос"),
        ]
    )
    db.flush()
    assert add_working_days(db, MONDAY, 5) == date(2026, 10, 19)
    assert add_working_days(db, MONDAY, 4) == date(2026, 10, 17)

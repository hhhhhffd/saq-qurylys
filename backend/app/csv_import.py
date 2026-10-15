"""Shared CSV parsing for bulk imports. Row problems are reported to the user in Russian."""

import csv
import io
from collections.abc import Iterator
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel

from app.errors import api_error

TRUE_VALUES = {"1", "true", "yes", "y", "да", "д", "+"}
FALSE_VALUES = {"0", "false", "no", "n", "нет", "н", "-"}
DELIMITERS = ",;\t"
MAX_ROWS = 20_000


class RowError(Exception):
    """A problem with one CSV row; the message is shown to the user."""


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    errors: list[ImportRowError] = []


def read_rows(raw: bytes, required: set[str], known: set[str]) -> Iterator[tuple[int, dict[str, str | None]]]:
    """Yield (row number as in a spreadsheet, values). Empty cells become None.

    Raises an API error for unreadable files or missing required columns. Unknown columns are ignored.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251", errors="replace")  # Excel in RU/KZ locales saves CSV as cp1251
    header_line = text.split("\n", 1)[0]
    delimiter = max(DELIMITERS, key=header_line.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [name.strip().lower() for name in next(reader)]
    except StopIteration as exc:
        raise api_error(422, "csv_empty", "Файл пуст") from exc
    missing = sorted(required - set(header))
    if missing:
        raise api_error(422, "csv_missing_columns", f"В файле нет обязательных столбцов: {', '.join(missing)}")
    columns = [(index, name) for index, name in enumerate(header) if name in known]
    count = 0
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue
        count += 1
        if count > MAX_ROWS:
            raise api_error(422, "csv_too_many_rows", f"В файле больше {MAX_ROWS} строк")
        yield (
            reader.line_num,
            {name: (cells[index].strip() or None) if index < len(cells) else None for index, name in columns},
        )


def require(row: dict[str, str | None], column: str) -> str:
    value = row.get(column)
    if value is None:
        raise RowError(f"Не заполнено обязательное поле «{column}»")
    return value


def parse_date(value: str | None, column: str) -> date | None:
    if value is None:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise RowError(f"Поле «{column}»: неверная дата «{value}», ожидается ГГГГ-ММ-ДД или ДД.ММ.ГГГГ")


def require_date(row: dict[str, str | None], column: str) -> date:
    parsed = parse_date(require(row, column), column)
    if parsed is None:  # require() guarantees a value, parse_date() either parses it or raises
        raise RowError(f"Не заполнено обязательное поле «{column}»")
    return parsed


def parse_float(value: str | None, column: str, low: float, high: float) -> float | None:
    if value is None:
        return None
    try:
        number = float(value.replace(",", "."))
    except ValueError as exc:
        raise RowError(f"Поле «{column}»: неверное число «{value}»") from exc
    if not low <= number <= high:
        raise RowError(f"Поле «{column}»: значение должно быть от {low:g} до {high:g}")
    return number


def parse_int(value: str | None, column: str, low: int, high: int) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise RowError(f"Поле «{column}»: неверное целое число «{value}»") from exc
    if not low <= number <= high:
        raise RowError(f"Поле «{column}»: значение должно быть от {low} до {high}")
    return number


def parse_bool(value: str | None, column: str) -> bool | None:
    if value is None:
        return None
    lowered = value.lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise RowError(f"Поле «{column}»: ожидается да/нет (1/0), получено «{value}»")


def parse_enum[E: StrEnum](value: str | None, column: str, enum_cls: type[E]) -> E | None:
    if value is None:
        return None
    try:
        return enum_cls(value.lower())
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_cls)
        raise RowError(f"Поле «{column}»: неизвестное значение «{value}», допустимо: {allowed}") from exc

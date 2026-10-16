"""One-off import of the open Kazreestr dataset from Ashyq Data: `python -m app.modules.registry_sync.ashyq`.

Dataset «Объекты с долевым участием в жилищном строительстве» (Smart Data Ukimet), CC BY 3.0 NZ. The file is
downloaded by hand (docs/DATA_SOURCES.md, OPEN_QUESTIONS 41) and is untrusted input: it is only parsed with `csv`.

Rows are per object, "пятно" or block, so a complex has several rows. They are grouped by normalized name and
builder, and each group is matched with an object of the city by name. What the dataset gives is a number whose
kind (permit of the local executive body or guarantee) it does not state, and no confirmation, so the number is
stored as a document on check (`checking`): the legal basis stays unknown ("Нужна проверка", 0 points, SPEC 6.0)
until a person checks it. The builder BIN is not in the dataset, so no developer is created (the BIN is mandatory).
An existing object is never changed; a group whose number the object already has is skipped, so a rerun is a no-op.
"""

import argparse
import csv
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_sessionmaker
from app.events import objects_changed
from app.models import ConstructionObject, Document, Territory
from app.models.enums import CheckSource, CheckStatus, DocType
from app.modules.registry_sync.records import clean_text, parse_date
from app.modules.registry_sync.upsert import (
    Changes,
    ObjectFacts,
    construction_status_on,
    create_object,
    local_today,
    normalize_name,
)

SOURCE_LABEL = "Казреестр (Ashyq Data, CC BY 3.0 NZ)"
SOURCE_URL = "https://ashyq.data.gov.kz/dataset/magda-ds-b80110e9-218a-42ba-b8c8-01fa5e4c82c8"
FILE_DATE = date(2026, 10, 12)
DEFAULT_TERRITORY_NAME = "Усть-Каменогорск"
DEFAULT_TERRITORY_CODE = "ust-kamenogorsk"
MATCH_THRESHOLD = 85

COLUMNS = {"id", "object_name", "builder_name", "address_name", "date_start", "number", "sdu_load_date"}
# ", Пятно 1", ", Блок А", ", Здание 2", ", Очередь 1" and "2 очередь": the part of a row name below the complex.
_PART = re.compile(r"(?:,\s*(?:пятно|блок|здание|очередь|секция|корпус)\b[^,]*|\s+\d+\s*очередь)\s*$", re.IGNORECASE)
_QUOTES = re.compile(r"[\"«»]")
_LEGAL_FORM = re.compile(r"\b(?:товарищество с ограниченной ответственностью|тоо)\b")
_REGION_PREFIX = re.compile(r"^Восточно-Казахстанская область,\s*")


class AshyqFormatError(ValueError):
    """The file is not the expected CSV."""


@dataclass
class Group:
    """Rows of one complex: the same normalized name and builder."""

    names: Counter[str] = field(default_factory=Counter)
    builders: Counter[str] = field(default_factory=Counter)
    addresses: Counter[str] = field(default_factory=Counter)
    numbers: dict[str, str] = field(default_factory=dict)  # number -> sdu_load_date of its first row
    row_ids: list[str] = field(default_factory=list)
    started: list[date] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.names.most_common(1)[0][0]

    @property
    def builder(self) -> str:
        return self.builders.most_common(1)[0][0]


@dataclass
class AshyqResult:
    rows_total: int = 0
    rows_in_territory: int = 0
    groups: int = 0
    created: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)  # existing object, a document added
    unchanged: list[str] = field(default_factory=list)  # existing object, every number already there
    changes: Changes = field(default_factory=Changes)


def complex_name(raw: str) -> str:
    """The name of the complex: row suffixes and quotes dropped, the «ЖК» prefix kept as the registry writes it."""
    name = raw.strip()
    while (stripped := _PART.sub("", name).strip()) != name:
        name = stripped
    return " ".join(_QUOTES.sub(" ", name).split())


def _builder_key(name: str) -> str:
    return " ".join(_LEGAL_FORM.sub(" ", _QUOTES.sub(" ", name.casefold())).split())


def read_groups(path: Path, territory_name: str) -> tuple[list[Group], int, int]:
    """(groups of the territory, rows in the file, rows of the territory)."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if missing := COLUMNS - set(reader.fieldnames or []):
            raise AshyqFormatError(f"в файле нет колонок: {', '.join(sorted(missing))}")
        rows = list(reader)
    wanted = territory_name.casefold()
    groups: dict[tuple[str, str], Group] = {}
    in_territory = 0
    for row in rows:
        address = clean_text(row["address_name"]) or ""
        if wanted not in address.casefold():
            continue
        in_territory += 1
        name = complex_name(row["object_name"] or "")
        builder = clean_text(row["builder_name"])
        if not normalize_name(name):
            raise AshyqFormatError(f"запись {row['id']}: пустое название")
        group = groups.setdefault((normalize_name(name), _builder_key(builder or "")), Group())
        group.names[name] += 1
        if builder:
            group.builders[builder] += 1
        group.addresses[_REGION_PREFIX.sub("", address)] += 1
        group.row_ids.append(row["id"])
        if number := clean_text(row["number"]):
            group.numbers.setdefault(number, clean_text(row["sdu_load_date"]) or "")
        if started := parse_date(row["date_start"]):
            group.started.append(started)
    return list(groups.values()), len(rows), in_territory


def _find_object(session: Session, territory_id: int, name: str) -> ConstructionObject | None:
    wanted = normalize_name(name)
    best: tuple[float, int] | None = None
    candidates = session.execute(
        select(ConstructionObject.id, ConstructionObject.name, ConstructionObject.aliases)
        .where(ConstructionObject.territory_id == territory_id, ConstructionObject.is_demo.is_(False))
        .order_by(ConstructionObject.id)
    )
    for object_id, object_name, aliases in candidates:
        score = max(fuzz.token_set_ratio(wanted, normalize_name(value)) for value in (object_name, *aliases))
        if score >= MATCH_THRESHOLD and (best is None or score > best[0]):
            best = (score, object_id)
    return session.get(ConstructionObject, best[1]) if best else None


def _document_note(group: Group, number: str, loaded: str) -> str:
    return (
        f"Запись в открытом наборе Казреестра «Объекты с долевым участием в жилищном строительстве» "
        f"(Smart Data Ukimet, {SOURCE_LABEL}), файл от {FILE_DATE.isoformat()}, загружена {loaded}: {SOURCE_URL}. "
        f"Номер в наборе: {number}; набор не указывает вид документа (разрешение МИО или гарантия) и не "
        f"подтверждает его действие, требуется ручная сверка. Застройщик по набору: {group.builder}"
        f" (БИН в наборе нет). Строк набора: {len(group.row_ids)}."
    )


def _add_documents(session: Session, obj: ConstructionObject, group: Group, changes: Changes) -> int:
    added = 0
    for number, loaded in sorted(group.numbers.items()):
        exists = session.scalar(
            select(Document.id).where(Document.object_id == obj.id, Document.number == number).limit(1)
        )
        if exists is not None:
            continue
        document = Document(
            object_id=obj.id,
            doc_type=DocType.guarantee if "ДПГ" in number else DocType.dsu_permit,
            number=number,
            issuer=None,
            check_status=CheckStatus.checking,
            check_source=CheckSource.kazreestr,
            note=_document_note(group, number, loaded),
        )
        session.add(document)
        session.flush()
        session.refresh(document)
        audit.record(session, None, "document.create", "document", document.id, None, audit.snapshot(document))
        changes.documents_created += 1
        changes.object_ids.add(obj.id)
        added += 1
    return added


def import_ashyq(session: Session, path: Path, territory_name: str, territory_code: str) -> AshyqResult:
    territory = session.scalar(select(Territory).where(Territory.code == territory_code))
    if territory is None:
        raise ValueError(f"unknown territory {territory_code!r}; run `python -m app.seed` first")
    groups, total, in_territory = read_groups(path, territory_name)
    result = AshyqResult(rows_total=total, rows_in_territory=in_territory, groups=len(groups))
    today = local_today(territory)
    for group in groups:
        obj = _find_object(session, territory.id, group.name)
        if obj is None:
            obj = create_object(
                session,
                territory_id=territory.id,
                name=group.name,
                facts=ObjectFacts(
                    aliases=[],
                    developer=None,
                    address=group.addresses.most_common(1)[0][0],
                    cadastral_number=None,
                    lat=None,
                    lon=None,
                    planned_completion=None,
                ),
                construction_status=construction_status_on(min(group.started, default=None), today),
                changes=result.changes,
            )
            _add_documents(session, obj, group, result.changes)
            result.created.append(obj.name)
        elif _add_documents(session, obj, group, result.changes):
            result.matched.append(f"{group.name} -> {obj.name}")
        else:
            result.unchanged.append(f"{group.name} -> {obj.name}")
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.modules.registry_sync.ashyq", description=__doc__)
    parser.add_argument("csv_path", type=Path, help="the dataset file downloaded from Ashyq Data")
    parser.add_argument("--territory-name", default=DEFAULT_TERRITORY_NAME, help="keep rows whose address has this")
    parser.add_argument("--territory-code", default=DEFAULT_TERRITORY_CODE, help="territory the objects belong to")
    parser.add_argument("--dry-run", action="store_true", help="report what would change and write nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    with get_sessionmaker()() as session:
        try:
            result = import_ashyq(session, args.csv_path, args.territory_name, args.territory_code)
        except (OSError, ValueError, KeyError) as exc:
            session.rollback()
            raise SystemExit(f"ashyq import failed: {exc}") from exc
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    if not args.dry_run:
        objects_changed(result.changes.object_ids)
    print(f"{'DRY RUN, nothing written. ' if args.dry_run else ''}Источник: {SOURCE_LABEL}, {SOURCE_URL}")
    print(
        f"Строк в файле: {result.rows_total}, по «{args.territory_name}»: {result.rows_in_territory}, "
        f"комплексов: {result.groups}"
    )
    for title, names in (
        ("создано объектов", result.created),
        ("сопоставлено, добавлены документы", result.matched),
        ("сопоставлено, без изменений", result.unchanged),
    ):
        print(f"{title}: {len(names)}")
        for name in names:
            print(f"  - {name}")
    print(f"документов создано: {result.changes.documents_created}")


if __name__ == "__main__":
    main()

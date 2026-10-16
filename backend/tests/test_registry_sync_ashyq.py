import csv
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ConstructionObject, Developer, Document
from app.models.enums import CheckSource, CheckStatus, DocType
from app.modules.registry_sync.ashyq import (
    AshyqFormatError,
    complex_name,
    import_ashyq,
    read_groups,
)
from tests.conftest import World

HEADER = [
    "id",
    "object_name",
    "builder_name",
    "auth_org_name",
    "address_name",
    "date_start",
    "date_end",
    "number",
    "sdu_load_date",
]
UST = "Восточно-Казахстанская область, г.Усть-Каменогорск, проспект Есенберлина, 92"
TUMAR = "Товарищество с ограниченной ответственностью «TUMAR Group»"
ROWS = [
    ["1", 'ЖК "Жаным"', 'ТОО "Biryuza Development"', "", UST, "", "", "ДПГ-23-16-068/155"],
    ["2", 'ЖК "Жаным", Блок А', 'ТОО "Biryuza Development"', "", UST, "2024-06-19", "2025-06-19", "ДПГ-23-16-068/155"],
    ["3", 'ЖК "Жаным", Блок Б', 'ТОО "Biryuza Development"', "", UST, "2024-06-06", "2025-05-06", "ДПГ-23-16-068/155"],
    ["4", "Tumar Towers Oskemen, Здание 1", TUMAR, "", UST, "2025-02-04", "2026-07-04", "KZ26VWE00002487"],
    ["5", "Tumar Towers Oskemen", TUMAR, "", UST, "", "", "KZ26VWE00002487"],
    ["6", "Золотой квадрат, Пятно 1", "ТОО НАУАН", "", UST, "", "", "ДПГ-25-16-078/194"],
    ["7", "Золотой квадрат, Пятно 2", "ТОО НАУАН", "", UST, "", "", "ДПГ-25-16-078/194"],
    ["8", "ЖК Almaty Tower", "ТОО Чужой", "", "г.Алматы, улица Абая, 1", "", "", "ДПГ-24-02-031/17"],
]


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "ashyq.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows([*row, "2026-06-15 17:35:09"] for row in ROWS)
    return path


def _add_object(db: Session, world: World, name: str) -> ConstructionObject:
    obj = ConstructionObject(territory_id=world.ust.id, name=name, address="свой адрес")
    db.add(obj)
    db.flush()
    return obj


def _documents(db: Session, obj: ConstructionObject) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.object_id == obj.id).order_by(Document.id)))


def test_complex_name_drops_parts_and_quotes() -> None:
    assert complex_name('ЖК "Жаным", Блок А') == "ЖК Жаным"
    assert complex_name("Золотой квадрат, Пятно 1") == "Золотой квадрат"
    assert complex_name('ЖК "Maxima City" 2 очередь, Пятно 4') == "ЖК Maxima City"
    assert complex_name("ЖК «ASYLTAS», Очередь 1") == "ЖК ASYLTAS"
    assert complex_name("Tumar Towers Oskemen, Здание 1") == "Tumar Towers Oskemen"


def test_rows_are_grouped_and_other_cities_ignored(csv_file: Path) -> None:
    groups, total, in_city = read_groups(csv_file, "Усть-Каменогорск")
    assert (total, in_city) == (8, 7)
    assert sorted(group.name for group in groups) == ["Tumar Towers Oskemen", "ЖК Жаным", "Золотой квадрат"]
    zhanym = next(group for group in groups if group.name == "ЖК Жаным")
    assert zhanym.row_ids == ["1", "2", "3"] and list(zhanym.numbers) == ["ДПГ-23-16-068/155"]


def test_missing_column_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("id,object_name\n1,x\n", encoding="utf-8")
    with pytest.raises(AshyqFormatError):
        read_groups(path, "Усть-Каменогорск")


def test_matched_object_is_kept_and_gets_the_number(db: Session, world: World, csv_file: Path) -> None:
    existing = _add_object(db, world, "ЖК ЖАНЫМ")
    result = import_ashyq(db, csv_file, "Усть-Каменогорск", "ust-kamenogorsk")
    assert result.matched == ["ЖК Жаным -> ЖК ЖАНЫМ"]
    assert sorted(result.created) == ["Tumar Towers Oskemen", "Золотой квадрат"]
    db.refresh(existing)
    assert (existing.name, existing.address, existing.developer_id) == ("ЖК ЖАНЫМ", "свой адрес", None)
    [document] = _documents(db, existing)
    assert document.number == "ДПГ-23-16-068/155" and document.doc_type is DocType.guarantee
    assert document.check_status is CheckStatus.checking and document.check_source is CheckSource.kazreestr
    assert document.note is not None and "ashyq.data.gov.kz/dataset/magda-ds-b80110e9" in document.note


def test_missing_object_is_created_with_unconfirmed_permit(db: Session, world: World, csv_file: Path) -> None:
    import_ashyq(db, csv_file, "Усть-Каменогорск", "ust-kamenogorsk")
    obj = db.scalars(select(ConstructionObject).where(ConstructionObject.name == "Tumar Towers Oskemen")).one()
    assert obj.territory_id == world.ust.id and not obj.is_demo
    assert obj.address == "г.Усть-Каменогорск, проспект Есенберлина, 92"
    [document] = _documents(db, obj)
    assert document.number == "KZ26VWE00002487" and document.check_status is CheckStatus.checking
    assert document.checked_at is None and document.checked_by is None
    assert db.scalar(select(func.count()).select_from(Developer)) == 0


def test_second_run_changes_nothing(db: Session, world: World, csv_file: Path) -> None:
    _add_object(db, world, "ЖК ЖАНЫМ")
    import_ashyq(db, csv_file, "Усть-Каменогорск", "ust-kamenogorsk")
    objects = db.scalar(select(func.count()).select_from(ConstructionObject))
    documents = db.scalar(select(func.count()).select_from(Document))
    again = import_ashyq(db, csv_file, "Усть-Каменогорск", "ust-kamenogorsk")
    assert again.created == [] and again.matched == [] and len(again.unchanged) == 3
    assert again.changes.documents_created == 0 and again.changes.objects_created == 0
    assert db.scalar(select(func.count()).select_from(ConstructionObject)) == objects
    assert db.scalar(select(func.count()).select_from(Document)) == documents

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import seed
from app.models import AdPost, AuditLog, Complaint, ConstructionObject, Developer, District, Document, Territory
from app.models.enums import CheckSource, CheckStatus, ConstructionStatus, DocType
from app.modules.registry_sync.pilot import PILOT_FILE, PilotResult, import_pilot
from tests.conftest import World

SNAPSHOT = json.loads(PILOT_FILE.read_text(encoding="utf-8"))
COLLECTED_AT = datetime(2026, 10, 12, 19, 0, tzinfo=UTC)  # 2026-10-13 00:00 in Asia/Almaty


@pytest.fixture
def pilot(db: Session) -> PilotResult:
    seed.seed_reference(db)
    seed.load_districts(db)
    return import_pilot(db)


def _object(db: Session, name: str) -> ConstructionObject:
    return db.scalars(select(ConstructionObject).where(ConstructionObject.name == name)).one()


def _documents(db: Session, obj: ConstructionObject) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.object_id == obj.id).order_by(Document.id)))


def test_packaged_snapshot_is_the_published_one() -> None:
    published = Path(__file__).resolve().parents[2] / "data" / "pilot" / PILOT_FILE.name
    if published.exists():
        assert published.read_bytes() == PILOT_FILE.read_bytes()


def test_union_of_krisha_objects_and_unclaimed_registry_records(db: Session, pilot: PilotResult) -> None:
    objects = list(db.scalars(select(ConstructionObject)))
    assert len(objects) == 28 and not any(obj.is_demo for obj in objects)
    assert pilot.krisha_objects == 26 and pilot.registry_only_objects == 2
    # Tumar Towers: the portal counts it as completed (commissioning date has passed) and krisha.kz agrees.
    assert pilot.skipped_completed == ["1077 ЖК Tumar Towers Oskemen"]
    assert {"ЖК Satti City", "МЖК Renesans"} <= {obj.name for obj in objects}
    assert pilot.changes.object_ids == {obj.id for obj in objects}


def test_matched_object_takes_facts_from_the_registry(db: Session, pilot: PilotResult) -> None:
    obj = _object(db, "ЖК Viva Life")
    assert obj.cadastral_number == "05-085-091-1658"
    assert (obj.lat, obj.lon) == (pytest.approx(49.920359), pytest.approx(82.618754))  # registry, not krisha.kz
    assert obj.planned_completion == obj.forecast_completion == date(2027, 8, 28)
    assert obj.construction_status is ConstructionStatus.active
    assert obj.aliases == []  # the registry name only differs by quotes
    developer = db.get(Developer, obj.developer_id)
    assert developer is not None
    assert (developer.bin, developer.name) == ("021040009554", 'ТОО "K-Story LTD"')
    assert developer.authorized_company == "ТОО «CRONUS STROY»"

    [document] = _documents(db, obj)
    assert document.doc_type is DocType.dsu_permit and document.number == "597/МҚЗТ-К-83у"
    assert document.issued_at == date(2026, 5, 8)
    assert document.check_status is CheckStatus.confirmed and document.check_source is CheckSource.housing_portal
    assert document.checked_at == COLLECTED_AT and document.checked_by is None
    assert document.note is not None
    assert document.note.startswith("Участие БВУ.")
    assert "https://api.homeportal.kz/api/v1/objects-detail/1398" in document.note


def test_guarantee_and_several_registry_records_for_one_object(db: Session, pilot: PilotResult) -> None:
    obj = _object(db, "ЖК ЖАНЫМ")
    documents = _documents(db, obj)
    assert [d.doc_type for d in documents] == [DocType.guarantee] * 3
    assert {d.number for d in documents} == {
        "ДПГ-23-16-068/155",
        "ДС № 2 к ДПГ-23-16-068/155",
        "ДС№4 к ДПГ-23-16-068/155",
    }
    assert obj.cadastral_number == "05-085-091-1400"  # one record has no number, another writes it with colons
    assert obj.planned_completion == date(2026, 2, 6)  # the latest commissioning date of the records
    assert _object(db, "ЖК ASYLTAS").cadastral_number is not None
    assert len(_documents(db, _object(db, "ЖК ASYLTAS"))) == 2


def test_large_coordinate_mismatch_keeps_krisha_position_and_says_so(db: Session, pilot: PilotResult) -> None:
    obj = _object(db, "ЖК Asyl Tau")
    assert (obj.lat, obj.lon) == (pytest.approx(49.889714), pytest.approx(82.620071))  # krisha.kz
    [document] = _documents(db, obj)
    assert document.check_status is CheckStatus.confirmed  # krisha.kz shows this very permit number
    assert document.note is not None and "оставлено по krisha.kz" in document.note


def test_krisha_object_missing_from_the_registry_gets_a_checking_placeholder(db: Session, pilot: PilotResult) -> None:
    obj = _object(db, "ЖК Easton")
    assert obj.developer_id is None and obj.planned_completion == date(2027, 12, 31)
    [document] = _documents(db, obj)
    assert document.doc_type is DocType.dsu_permit and document.check_status is CheckStatus.checking
    assert document.number is None and document.checked_at is None
    assert document.note is not None
    assert document.note.startswith("требуется ручная сверка: в выгрузке реестра КЖК от 2026-10-13 не найден.")
    assert "https://krisha.kz/complex/show/ust-kamenogorsk/" in document.note


def test_unverified_bin_is_not_entered_but_left_as_a_lead(db: Session, pilot: PilotResult) -> None:
    obj = _object(db, "ЖК Green Leaf")
    assert obj.developer_id is None
    assert db.scalar(select(func.count()).select_from(Developer).where(Developer.bin == "160640005003")) == 0
    [document] = _documents(db, obj)
    assert document.note is not None
    assert "160640005003" in document.note and "statsnet.co" in document.note and "не внесён" in document.note


def test_krisha_displayed_document_is_quoted_but_not_trusted(db: Session, pilot: PilotResult) -> None:
    [document] = _documents(db, _object(db, "ЖК Престиж"))
    assert document.check_status is CheckStatus.checking and document.number is None
    assert document.note is not None and "ДПГ-22-16-055/120" in document.note


def test_unconfirmed_match_is_not_linked(db: Session, pilot: PilotResult) -> None:
    """Satti City 2 on krisha.kz and `Satti City` in the registry: the snapshot itself says "не подтверждено"."""
    krisha = _object(db, "ЖК Satti City 2")
    [placeholder] = _documents(db, krisha)
    assert placeholder.check_status is CheckStatus.checking
    assert placeholder.note is not None and "№ 1452" in placeholder.note
    registry = _object(db, "ЖК Satti City")
    [document] = _documents(db, registry)
    assert document.check_status is CheckStatus.confirmed and document.number == "KZ05PDD00004080"
    assert krisha.id != registry.id


def test_registry_coordinates_outside_the_city_are_not_used(db: Session, pilot: PilotResult) -> None:
    obj = _object(db, "МЖК Renesans")
    assert obj.lat is None and obj.district_id is None
    [document] = _documents(db, obj)
    assert document.note is not None and "признаны ошибочными" in document.note


def test_districts_come_from_point_in_polygon(db: Session, pilot: PilotResult) -> None:
    located = db.scalar(
        select(func.count()).select_from(ConstructionObject).where(ConstructionObject.location.is_not(None))
    )
    assert located == 27 and pilot.without_district == 0
    outside = db.scalar(
        select(func.count())
        .select_from(ConstructionObject)
        .join(District, District.id == ConstructionObject.district_id)
        .where(func.ST_Contains(District.boundary, ConstructionObject.location).is_not(True))
    )
    with_district = db.scalar(
        select(func.count()).select_from(ConstructionObject).where(ConstructionObject.district_id.is_not(None))
    )
    assert outside == 0 and with_district == 27


def test_only_legal_entities_are_imported(db: Session, pilot: PilotResult) -> None:
    """No director, founder or contact of a person: the registry facts are about companies (SPEC D19)."""
    developers = list(db.scalars(select(Developer)))
    assert developers
    assert all(d.director is None and d.founders == [] and d.phones == [] for d in developers)
    assert all(re.fullmatch(r"[0-9]{12}", d.bin) for d in developers)
    notes = " ".join(note for note in db.scalars(select(Document.note)) if note)
    assert "@" not in notes and "+7" not in notes  # no e-mail addresses or phone numbers


def test_no_complaints_ads_or_judgement_are_added(db: Session, pilot: PilotResult) -> None:
    assert db.scalar(select(func.count()).select_from(Complaint)) == 0
    assert db.scalar(select(func.count()).select_from(AdPost)) == 0
    assert (
        db.scalar(
            select(func.count()).select_from(ConstructionObject).where(ConstructionObject.prior_violations.is_not(None))
        )
        == 0
    )


def test_import_is_audited_without_a_user(db: Session, pilot: PilotResult) -> None:
    actions = {(row.action, row.user_id) for row in db.scalars(select(AuditLog))}
    assert {("object.create", None), ("document.create", None), ("developer.create", None)} <= actions


def test_repeated_import_changes_nothing(db: Session, pilot: PilotResult) -> None:
    before = db.scalar(select(func.count()).select_from(AuditLog))
    again = import_pilot(db)
    assert (again.changes.objects_created, again.changes.objects_updated) == (0, 0)
    assert (again.changes.documents_created, again.changes.documents_updated) == (0, 0)
    assert again.changes.object_ids == set()
    assert db.scalar(select(func.count()).select_from(ConstructionObject)) == 28
    assert db.scalar(select(func.count()).select_from(Document)) == 31
    assert db.scalar(select(func.count()).select_from(AuditLog)) == before


def test_repeated_import_keeps_what_people_changed(db: Session, world: World, pilot: PilotResult) -> None:
    obj = _object(db, "ЖК Viva Life")
    obj.address = "ул. Исправленная, 1"
    obj.forecast_completion = date(2028, 1, 31)
    [document] = _documents(db, obj)
    document.checked_by = world.users["mio_ust"].id
    document.check_status = CheckStatus.not_found
    db.flush()

    import_pilot(db)
    db.refresh(obj)
    db.refresh(document)
    assert obj.address == "ул. Исправленная, 1" and obj.forecast_completion == date(2028, 1, 31)
    assert document.check_status is CheckStatus.not_found  # a person's decision is not overwritten


def test_import_completes_an_object_that_already_exists(db: Session) -> None:
    """An object entered by hand (same cadastral number) is completed, never duplicated or overwritten."""
    seed.seed_reference(db)
    seed.load_districts(db)
    city = db.scalars(select(Territory).where(Territory.code == "ust-kamenogorsk")).one()
    manual = ConstructionObject(territory_id=city.id, name="Вива Лайф (вручную)", cadastral_number="05-085-091-1658")
    db.add(manual)
    db.flush()

    import_pilot(db)
    assert db.scalars(select(ConstructionObject).where(ConstructionObject.name == "ЖК Viva Life")).first() is None
    assert db.scalar(select(func.count()).select_from(ConstructionObject)) == 28
    db.refresh(manual)
    assert manual.name == "Вива Лайф (вручную)"
    assert manual.developer_id is not None and manual.planned_completion == date(2027, 8, 28)
    assert len(_documents(db, manual)) == 1


class _Borrowed:
    """Lends the test session to code that opens its own session from a factory."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *exc: object) -> None:
        return None


def test_run_pilot_queues_rescoring_of_new_and_changed_objects_only(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed.seed_reference(db)
    seed.load_districts(db)
    queued: list[set[int]] = []
    monkeypatch.setattr(seed, "objects_changed", lambda ids: queued.append(set(ids)))

    seed.run_pilot(lambda: _Borrowed(db))  # type: ignore[arg-type]
    seed.run_pilot(lambda: _Borrowed(db))  # type: ignore[arg-type]
    assert len(queued[0]) == 28 and queued[1] == set()


def test_invalid_snapshot_is_reported(db: Session, tmp_path: Path) -> None:
    seed.seed_reference(db)
    broken = tmp_path / "snapshot.json"
    broken.write_text(json.dumps({"meta": {}, "objects": [], "homeportal_registry_objects_vko": []}))
    with pytest.raises(ValueError, match="collected_at"):
        import_pilot(db, broken)

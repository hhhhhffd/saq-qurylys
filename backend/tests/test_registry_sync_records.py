import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.models.enums import DocType
from app.modules.registry_sync import records
from app.modules.registry_sync.records import RegistryFormatError
from app.modules.registry_sync.upsert import normalize_name

FIXTURES = Path(__file__).parent / "fixtures" / "homeportal"


def _detail(registry_id: int) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((FIXTURES / f"detail_{registry_id}.json").read_text(encoding="utf-8"))
    return body


def test_detail_of_a_bank_participation_permit() -> None:
    record = records.from_detail(1398, _detail(1398))
    assert record.basis == "Участие БВУ" and record.doc_type is DocType.dsu_permit and record.basis_is_known
    assert record.number == "597/МҚЗТ-К-83у"
    assert (record.issued_at, record.started_at, record.commissioning_at) == (
        date(2026, 5, 8),
        date(2026, 4, 28),
        date(2027, 8, 28),
    )
    assert record.city == "Усть-Каменогорск"
    assert record.cadastral_number == "05-085-091-1658"
    assert (record.lat, record.lon) == (49.920359, 82.618754)
    assert record.developer_bin == "021040009554" and record.developer_name == 'ТОО "K-Story LTD"'
    assert record.authorized_company == "ТОО «CRONUS STROY»"
    assert record.bank == 'АО "Евразийский банк"'
    assert record.detail_url == "https://api.homeportal.kz/api/v1/objects-detail/1398"
    assert record.object_name == "ЖК Viva Life"


def test_guarantee_maps_to_guarantee_with_kzhk_as_issuer() -> None:
    record = records.from_detail(1027, _detail(1027))
    assert record.doc_type is DocType.guarantee and record.issuer == "АО «КЖК»" and record.basis_is_known


def test_cadastral_number_written_with_colons_is_normalized() -> None:
    assert records.from_detail(807, _detail(807)).cadastral_number == "05-085-091-1400"


def test_missing_cadastral_number_and_completed_status() -> None:
    record = records.from_detail(953, _detail(953))
    assert record.cadastral_number is None
    assert record.is_completed(date(2026, 10, 13))  # commissioning 2025-12-19 has passed
    assert not records.from_detail(1398, _detail(1398)).is_completed(date(2026, 10, 13))


def test_unknown_basis_is_recorded_but_not_trusted() -> None:
    body = _detail(1398)
    body["data"]["basicData"]["authority"]["name"] = "Иное основание"
    record = records.from_detail(1398, body)
    assert record.doc_type is DocType.dsu_permit and not record.basis_is_known


def test_detail_without_basic_data_is_rejected() -> None:
    with pytest.raises(RegistryFormatError):
        records.from_detail(1, {"data": {}})
    with pytest.raises(RegistryFormatError):
        records.from_detail(1, ["not", "an", "object"])


def test_snapshot_record_matches_the_live_shape() -> None:
    item = {
        "registry_id": 1398,
        "name": 'ЖК "Viva Life"',
        "basis": "Участие БВУ",
        "permit_or_guarantee_number": "597/МҚЗТ-К-83у",
        "issue_date": "08.05.2026",
        "construction_start_date": "28.04.2026",
        "commissioning_date": "28.08.2027",
        "address": "г. Усть-Каменогорск, пр. И. Есенберлина, д. 88/1",
        "cadastral_number": "05-085-091-1658",
        "lat": 49.920359,
        "lon": 82.618754,
        "developer": {"name": 'ТОО "K-Story LTD"', "bin": "021040009554"},
        "authorized_company": {"name": "ТОО «CRONUS STROY»", "bin": "210540016344"},
        "bank": 'АО "Евразийский банк"',
    }
    assert records.from_snapshot(item) == records.from_detail(1398, _detail(1398))


def test_coordinates_outside_the_country_are_dropped() -> None:
    assert records.parse_coordinates("49.9", "82.6") == (49.9, 82.6)
    assert records.parse_coordinates("0", "0") is None
    assert records.parse_coordinates(None, "82.6") is None
    assert records.parse_coordinates("abc", "82.6") is None


def test_dates_and_names() -> None:
    assert records.parse_date("07.10.2026") == date(2026, 10, 7)
    assert records.parse_date("2026-10-07") == date(2026, 10, 7)
    assert records.parse_date("") is None and records.parse_date("31.02.2026") is None
    assert normalize_name('МЖК "PARK LINE"') == normalize_name("ЖК Park Line") == "park line"
    assert normalize_name("Клубный дом Чистое небо") == "чистое небо"

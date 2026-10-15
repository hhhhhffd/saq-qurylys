"""Records of the housing portal registry (homeportal.kz, АО «КЖК») in one normalized shape.

Two sources produce them: the pilot snapshot in `app/seed_data/pilot` and the live API (`objects-detail/<id>`).
Both carry the same facts, so the import and the sync share everything after parsing.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.models.enums import DocType

API_BASE = "https://api.homeportal.kz/api/v1"

# Bases of raising money from shareholders. The permit of the local executive body (МИО) is issued under the first
# two (OPEN_QUESTIONS 12); a guarantee of АО «КЖК» is a document of its own.
_PERMIT_BASES = frozenset({"разрешение мио", "участие бву"})
_GUARANTEE_MARK = "гарант"

ISSUER_PERMIT = "МИО"
ISSUER_GUARANTEE = "АО «КЖК»"

# Kazakhstan lies roughly within these bounds; anything else is a data entry error.
_LAT_RANGE = (40.0, 56.0)
_LON_RANGE = (46.0, 88.0)

_CITY_PREFIX = re.compile(r"^\s*г\.?\s*", re.IGNORECASE)


class RegistryFormatError(ValueError):
    """The registry answered with something other than the known structure."""


@dataclass(frozen=True)
class RegistryRecord:
    registry_id: int
    name: str
    basis: str
    number: str | None
    issued_at: date | None
    started_at: date | None
    commissioning_at: date | None
    address: str | None
    city: str | None
    cadastral_number: str | None
    lat: float | None
    lon: float | None
    developer_bin: str | None
    developer_name: str | None
    authorized_company: str | None
    bank: str | None

    @property
    def detail_url(self) -> str:
        return f"{API_BASE}/objects-detail/{self.registry_id}"

    @property
    def doc_type(self) -> DocType:
        return DocType.guarantee if _GUARANTEE_MARK in self.basis.casefold() else DocType.dsu_permit

    @property
    def issuer(self) -> str:
        return ISSUER_GUARANTEE if self.doc_type is DocType.guarantee else ISSUER_PERMIT

    @property
    def basis_is_known(self) -> bool:
        """A basis the mapping rules cover. A new one is recorded but not trusted until a person checks it."""
        folded = self.basis.casefold()
        return folded in _PERMIT_BASES or _GUARANTEE_MARK in folded

    @property
    def object_name(self) -> str:
        """Registry names carry straight quotes (ЖК "Viva Life"); object names in SAQ do not."""
        return " ".join(self.name.replace('"', " ").replace("«", " ").replace("»", " ").split())

    def is_completed(self, today: date) -> bool:
        """The portal counts a record as completed once its commissioning date has passed."""
        return self.commissioning_at is not None and self.commissioning_at < today


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def parse_date(value: Any) -> date | None:
    """`DD.MM.YYYY` as the registry writes it; ISO dates are accepted too. Anything else is unknown."""
    text = clean_text(value)
    if text is None:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_coordinates(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        lat_value, lon_value = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (_LAT_RANGE[0] <= lat_value <= _LAT_RANGE[1] and _LON_RANGE[0] <= lon_value <= _LON_RANGE[1]):
        return None
    return lat_value, lon_value


def normalize_cadastral(value: Any) -> str | None:
    """The registry writes 05-085-091-1400 and 05:085:091:1400 for the same kind of number."""
    text = clean_text(value)
    return text.replace(":", "-") if text else None


def city_name(address_or_city: str | None) -> str | None:
    """`г. Усть-Каменогорск` and `г. Усть-Каменогорск, пр. ...` both give `Усть-Каменогорск`."""
    text = clean_text(address_or_city)
    if text is None:
        return None
    return _CITY_PREFIX.sub("", text.split(",")[0]).strip() or None


def _named(item: Any) -> tuple[str | None, str | None]:
    """(BIN, name) of a company entry; the snapshot and the API both use `bin` and `name`."""
    if not isinstance(item, dict):
        return None, None
    return clean_text(item.get("bin")), clean_text(item.get("name"))


def from_snapshot(item: dict[str, Any]) -> RegistryRecord:
    """A registry record of the pilot snapshot (`homeportal_registry_objects_vko` or a krisha match)."""
    developer_bin, developer_name = _named(item.get("developer"))
    coordinates = parse_coordinates(item.get("lat"), item.get("lon"))
    return RegistryRecord(
        registry_id=int(item["registry_id"]),
        name=str(item["name"]),
        basis=str(item["basis"]),
        number=clean_text(item.get("permit_or_guarantee_number")),
        issued_at=parse_date(item.get("issue_date")),
        started_at=parse_date(item.get("construction_start_date")),
        commissioning_at=parse_date(item.get("commissioning_date")),
        address=clean_text(item.get("address")),
        city=city_name(item.get("address")),
        cadastral_number=normalize_cadastral(item.get("cadastral_number")),
        lat=coordinates[0] if coordinates else None,
        lon=coordinates[1] if coordinates else None,
        developer_bin=developer_bin,
        developer_name=developer_name,
        authorized_company=_named(item.get("authorized_company"))[1],
        bank=clean_text(item.get("bank")),
    )


def _section(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise RegistryFormatError(f"в ответе реестра нет раздела {key!r}")
    return value


def _optional_section(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def from_detail(registry_id: int, body: Any) -> RegistryRecord:
    """A record from the `objects-detail/<id>` answer of the registry."""
    if not isinstance(body, dict):
        raise RegistryFormatError("ответ реестра не является объектом JSON")
    data = _section(body, "data")
    basic = _section(data, "basicData")
    location = _optional_section(data, "locationData")
    companies = _optional_section(data, "companyData")
    authority = basic.get("authority")
    basis = clean_text(authority.get("name")) if isinstance(authority, dict) else None
    name = clean_text(basic.get("name"))
    if basis is None or name is None:
        raise RegistryFormatError("в записи реестра нет названия или основания")
    developer_bin, developer_name = _named(basic.get("developerData") or companies.get("developerData"))
    city = basic.get("city")
    bank = basic.get("name_of_stb")
    coordinates = parse_coordinates(location.get("latitude"), location.get("longitude"))
    return RegistryRecord(
        registry_id=registry_id,
        name=name,
        basis=basis,
        number=clean_text(basic.get("warranty_number")),
        issued_at=parse_date(basic.get("issue_date")),
        started_at=parse_date(basic.get("start_date")),
        commissioning_at=parse_date(basic.get("commissioning_date")),
        address=clean_text(basic.get("address")),
        city=city_name(city.get("name_ru")) if isinstance(city, dict) else city_name(basic.get("address")),
        cadastral_number=normalize_cadastral(location.get("cadastral_number")),
        lat=coordinates[0] if coordinates else None,
        lon=coordinates[1] if coordinates else None,
        developer_bin=developer_bin,
        developer_name=developer_name,
        authorized_company=_named(companies.get("authorizedData"))[1],
        bank=clean_text(bank.get("name_ru")) if isinstance(bank, dict) else None,
    )

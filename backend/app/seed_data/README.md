# Seed data files

`python -m app.seed` loads these optional files when they exist. All are loaded idempotently.
Files are UTF-8. A missing file is skipped.

## `districts.geojson`

GeoJSON `FeatureCollection`. Each feature is a district polygon (Polygon or MultiPolygon, WGS84):

```json
{"type": "Feature",
 "properties": {"name": "Центральный", "territory_code": "ust-kamenogorsk"},
 "geometry": {"type": "Polygon", "coordinates": [[[82.6, 49.9], ...]]}}
```

`territory_code` is optional (default `ust-kamenogorsk`) and must be an existing city. Districts are matched by
`(city, name)`: re-running updates the boundary.

## `holidays.json`

Production calendar overrides. Saturdays and Sundays are days off by default.

```json
[{"day": "2026-12-16", "kind": "holiday", "name": "День Независимости"},
 {"day": "2026-12-19", "kind": "workday", "name": "Рабочая суббота (перенос)"}]
```

`kind`: `holiday` (day off) or `workday` (a weekend day that is worked). Matched by `day`; re-running updates
`kind` and `name`.

## `demo_objects.json` (only with `--demo`)

All demo objects are created with `is_demo=true`. Use fictional names and BINs only (see
`docs/OPEN_QUESTIONS.md`, item 1). An object that already exists (`is_demo` and same `name`) is skipped together
with its children, so re-running never duplicates data. Unknown keys are rejected.

```json
{
  "developers": [
    {"bin": "999999999999", "name": "ТОО «Вымышленный»", "director": "Иванов И. И.",
     "founders": ["Иванов И. И."], "authorized_company": null, "phones": ["+7 701 000 00 01"]}
  ],
  "objects": [
    {
      "name": "ЖК «Вымышленный»",
      "aliases": ["Вымышленный квартал"],
      "territory_code": "ust-kamenogorsk",
      "district": "Центральный",
      "developer_bin": "999999999999",
      "address": "ул. Примерная, 1",
      "cadastral_number": "05-123-000-001",
      "land_purpose": "для строительства жилого комплекса",
      "lat": 49.95, "lon": 82.61,
      "planned_completion": "2027-12-31",
      "forecast_completion": "2028-06-30",
      "construction_status": "active",
      "stalled_since": null,
      "prior_violations": null,
      "readiness_claimed_pct": null,
      "documents": [
        {"doc_type": "dsu_permit", "number": "12-ДСУ", "issued_at": "2026-03-01", "issuer": "МИО",
         "check_status": "not_found", "check_source": "kazreestr", "note": null}
      ],
      "complaints": [
        {"received_at": "2026-09-01", "source": "eotinish", "external_id": "EO-1", "is_collective": true,
         "signatories_count": 12, "summary": "...", "status": "new", "confirmed_payments": false}
      ],
      "inspections": [
        {"inspected_at": "2026-08-01", "readiness_pct": 35, "lat": 49.95, "lon": 82.61, "note": "каркас"}
      ],
      "linked_entities": [
        {"kind": "phone", "value": "+77010000001", "note": null}
      ],
      "ads": [
        {"platform": "instagram", "url": "https://example.invalid/p/1", "external_id": "p1", "author": "vymyshlennyi",
         "published_at": "2026-10-01T10:00:00+05:00", "text": "Бронь квартир открыта",
         "phones": ["8 701 000 00 01"], "is_outdoor": false, "lat": null, "lon": null,
         "payment_schemes": ["booking"], "claimed_readiness_pct": 60, "price_before_completion": false,
         "status": "captured"}
      ]
    }
  ]
}
```

Rules:

- `developer_bin` must reference a developer from `developers` (or an existing one).
- `readiness_actual_pct` is taken from the latest inspection by date; `readiness_claimed_pct` from the object
  field if set, otherwise from the latest ad with `claimed_readiness_pct`.
- Ads are stored as already captured publications linked to the object; phrase hits are not created here (the
  NLP pipeline does that when it processes the text). Evidence files are not part of the demo data.
- Enum values: `doc_type`, `check_status`, `check_source`, `source`, `status`, `kind`, `platform`,
  `payment_schemes` and `construction_status` use the codes from `docs/SPEC.md` section 3.
- After loading, `risk.recalc_object` is requested for every new object so the risk module can score it.

`--demo` also creates users `demo_admin`, `demo_mio` (Усть-Каменогорск), `demo_gask` (Усть-Каменогорск) and
`demo_police` (whole region). Their password is `DEMO_USER_PASSWORD` if set, otherwise random and printed once.

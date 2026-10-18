# Seed data files

`python -m app.seed` loads these optional files when they exist. All are loaded idempotently.
Files are UTF-8. A missing file is skipped. `districts.geojson` and `holidays.json` are always loaded;
`demo_objects.json` only with `--demo`, the pilot snapshot only with `--pilot`.

## `districts.geojson`

GeoJSON `FeatureCollection`. Each feature is a district polygon (Polygon or MultiPolygon, WGS84):

```json
{"type": "Feature",
 "properties": {"name": "Центральный", "territory_code": "ust-kamenogorsk"},
 "geometry": {"type": "Polygon", "coordinates": [[[82.6, 49.9], ...]]}}
```

`territory_code` is optional (default `ust-kamenogorsk`) and must be an existing city. Districts are matched by
`(city, name)`: re-running updates the boundary. Other properties of the features (`bank`, `group`, `approximate`,
`area_km2`, `seed`, `notes`) and the collection-level metadata are ignored by the loader. The polygons are
approximate (OSM-derived, no official boundaries exist): they serve the district filter only.

## `holidays.json`

Production calendar overrides. Saturdays and Sundays are days off by default.

```json
[{"day": "2026-12-16", "kind": "holiday", "name": "День Независимости"},
 {"day": "2026-12-19", "kind": "workday", "name": "Рабочая суббота (перенос)"}]
```

`kind`: `holiday` (day off) or `workday` (a weekend day that is worked). Matched by `day`; re-running updates
`kind` and `name`.

## `demo_objects.json` (only with `--demo`)

Fictional data only (docs/OPEN_QUESTIONS.md, item 1; SPEC D19): objects, developers, people, phones
(`+7 700 000 xx xx`) and URLs (`https://example.invalid/...`) are invented, BINs start with `99`. All demo objects
and all demo ads are created with `is_demo=true`. An object that already exists (`is_demo` and same `name`) is
skipped together with its children, so re-running never duplicates data. Unknown keys are rejected.

The shipped file holds 16 objects and 14 ads, built so that scoring (SPEC section 6) gives:

| Object | What it shows | Score / zone |
|---|---|---|
| ЖК «Северный бриз» (alias «Сценарий A») | legal basis never checked + paid booking (R2, R3) | 35 yellow |
| ЖК «Золотая осень» (alias «Сценарий B») | guarantee and MIO permit both checked, not found + deposit (R1, R2, R3) | 70 red |
| ЖК «Тихая гавань» (alias «Сценарий C») | guarantee confirmed, no MIO permit + ordinary advertising (R3) | 10 green |
| ЖК «Хрустальный город» | not found + «инвестиционный договор», «договор резервирования» on a site, a billboard and Telegram | 70 red |
| ЖК «Эдельвейс» | R1 alone, no advertising | 35 yellow |
| ЖК «Тополиная аллея» | verified collective complaint (R4) + ad | 25 yellow |
| ЖК «Кедровый квартал» | claimed 70% vs 35% at the inspection (R5) + installment ad | 45 yellow |
| ЖК «Лазурный берег» | confirmed guarantee, but «рассрочка от застройщика» still counts (R2) | 35 yellow |
| ЖК «Звёздный путь», ЖК «Новая эра» | stalled for 68 days / planned date passed 120 days ago (R6) | 5 / 15 green |
| ЖК «Облачный» | MIO permit still `checking`: flag «Нужна проверка», no points | 10 green |
| four more | clean cards | 0-10 green |

Every risky wording in the texts is one the seeded dictionary matches (a test checks it). `seed.py` adds the wording of
the case to the dictionary variants («внесите депозит», «цена до завершения»), also in existing databases.

```json
{
  "developers": [
    {"bin": "990000000011", "name": "ТОО «Вымышленный»", "director": "Иванов И. И.",
     "founders": ["Иванов И. И."], "authorized_company": null, "phones": ["+7 700 000 01 00"]}
  ],
  "objects": [
    {
      "name": "ЖК «Вымышленный»",
      "aliases": ["Вымышленный квартал", "Сценарий A"],
      "territory_code": "ust-kamenogorsk",
      "district": "Центр",
      "developer_bin": "990000000011",
      "address": "ул. Примерная, 1",
      "cadastral_number": "05-999-000-0001",
      "land_purpose": "для строительства жилого комплекса",
      "lat": 49.95, "lon": 82.62,
      "planned_completion": "+330d",
      "forecast_completion": "+330d",
      "construction_status": "active",
      "stalled_since": null,
      "prior_violations": null,
      "readiness_claimed_pct": null,
      "documents": [
        {"doc_type": "guarantee", "number": "ДПГ-26-16-901/301", "issued_at": "-240d", "issuer": "АО «КЖК»",
         "check_status": "confirmed", "check_source": "housing_portal", "checked_at": "-12d", "note": null}
      ],
      "complaints": [
        {"received_at": "-40d", "source": "eotinish", "external_id": "EO-DEMO-1", "is_collective": true,
         "signatories_count": 28, "summary": "...", "status": "in_review", "confirmed_payments": false,
         "is_verified": true}
      ],
      "inspections": [
        {"inspected_at": "-9d", "readiness_pct": 35, "lat": 49.95, "lon": 82.62, "note": "каркас"}
      ],
      "linked_entities": [
        {"kind": "phone", "value": "+77000000101", "note": "Офис продаж"}
      ],
      "ads": [
        {"platform": "instagram", "url": "https://example.invalid/instagram/demo/p1", "external_id": "demo-p1",
         "author": "demo", "published_at": "-3d", "text": "Платная бронь квартир. +7 700 000 01 01",
         "phones": ["+7 700 000 01 01"], "is_outdoor": false, "lat": null, "lon": null,
         "payment_schemes": ["booking"], "claimed_readiness_pct": null, "price_before_completion": false,
         "status": "captured"}
      ]
    }
  ]
}
```

Rules:

- **Relative dates.** Every date or datetime field (`planned_completion`, `forecast_completion`, `stalled_since`,
  `issued_at`, `checked_at`, `received_at`, `inspected_at`, `published_at`) accepts `"-2d"`, `"+330d"` or `"-36h"`:
  the moment of loading plus the offset. Dates are taken in the city time zone, datetimes are UTC. Absolute ISO values
  work as before. This keeps the demo current: ads stay inside the analysis window, inspections fresh, deadlines ahead.
- `developer_bin` must reference a developer from `developers` (or an existing one).
- `district` is a name from `districts.geojson`; without it the district is found by point in polygon.
- `readiness_actual_pct` is taken from the latest inspection by date; `readiness_claimed_pct` from the object
  field if set, otherwise from the latest ad with `claimed_readiness_pct`.
- Documents with a status other than `checking` are recorded as checked by `demo_mio` (when that user exists).
  `checked_at` is optional and should be given for checked documents.
- A complaint with `is_verified: true` is recorded as verified by `demo_mio` just now (R4 counts verified collective
  complaints only).
- Ads are stored as already captured publications linked to the object (`link_method=manual`), always with
  `is_demo=true`; phrase hits are not created here (the NLP pipeline does that). Evidence files are not part of the
  demo data. `platform: "outdoor"` ads have no URL and carry `lat`/`lon`.
- Enum values: `doc_type`, `check_status`, `check_source`, `source`, `status`, `kind`, `platform`,
  `payment_schemes` and `construction_status` use the codes from `docs/SPEC.md` section 3.
- After loading, every new ad is sent through `nlp.analyze` -> `nlp.link` (-> `nlp.llm_extract` when `LLM_ENABLED=true`;
  its findings are hypotheses and do not change the score) -> `risk.recalc_object` (Celery tasks
  addressed by name, one chain per ad), and objects without ads are rescored with `risk.recalc_object` directly.
  Nothing happens when `EVENTS_ENABLED=false`.

`--demo` also creates users `demo_admin`, `demo_mio` (Усть-Каменогорск), `demo_gask` (Усть-Каменогорск) and
`demo_police` (whole region). Their password is `DEMO_USER_PASSWORD` if set, otherwise random and printed once.

## `demo_versions.json` (only with `--demo`)

The story of SPEC 10.6, «Удалили — а у нас осталось»: a fictional object ЖК «Малахит» (own developer, own phones
`+7 700 000 91 xx`, so no other object is linked to it and no other score moves) with one Telegram post. Read by
`app/seed_versions.py`, loaded after `demo_objects.json`, idempotent. The shape is
`{"developers": [...], "object": {...}, "history": {...}}`; `developers` and `object` are as in `demo_objects.json`,
the object has exactly one ad (status `removed_saved`), `history` says what happened to it:

- `captured`: when the original was captured (relative, `"-90h"`); `original_screenshot`: a file of this directory
  stored as the screenshot evidence of that moment.
- `versions`: later texts, each with `observed_after_hours` since the capture, `source` (`capture`, `collector` or
  `recheck`) and an optional `screenshot` file stored as the evidence of that moment.
- `removed_after_hours`: when the removal was found (`removed_detected_at`, `last_checked_at`).

The screenshots (`demo_versions_original.png`, `demo_versions_edited.png`) show a synthetic post of a fictional
channel. They are stored without an RFC 3161 token: a token states when it was issued and cannot be backdated.
The object scores 35 yellow: the saved original offers a booking, and a removed post still counts (R2 + R3).

## `demo_network.json` (only with `--demo`)

The story "один телефон на троих" (SPEC 10.3), in the same format and with the same fictional-data rules as
`demo_objects.json` (it is read by the same loader, `seed_demo_objects(session, "demo_network.json")`, and is loaded right
after it). Three developers (BIN `99214…`, `99234…`, `99254…`), one ЖК each, one sales phone `+7 700 000 20 01` on all
three objects and one advertising account, `instagram.com/prime_estate_demo`, named on two of the cards and in the texts of
all four ads. Their own phones are `+7 700 000 21 00`, `22 00`, `23 00`. Nothing here is shared with `demo_objects.json`
(a test checks phones, BINs, names, cadastral numbers, distance between points and that every score there stays as it was):

| Object | Score / zone |
|---|---|
| ЖК «Ривьера Парк» | 70 red (guarantee and MIO permit not found + «внесите депозит») |
| ЖК «Меридиан Сити» | 35 yellow (guarantee confirmed + «рассрочка от застройщика») |
| ЖК «Сосновый бор» | 10 green (guarantee confirmed + ordinary advertising) |

The link graph then shows two findings (the phone and the account, three developers each), and `prime_estate_demo` is
offered as a candidate source until someone accepts or dismisses it.

## `demo_history.json` (only with `--demo`)

Older dated facts of the demo objects, for the time machine of the map (SPEC 10.5). Fictional, like the rest of the demo
data. Applied once, to the objects that `--demo` has just created (matched by `name`); repeating it adds nothing.
Unknown keys are rejected. Per object:

- `ads`: older publications, same fields as in `demo_objects.json`. They are dated 32 to 175 days back, so they lie
  outside the analysis window (30 days) and do not change a current score.
- `complaints`: older complaints, same fields as in `demo_objects.json` (keep them unverified or closed).
- `document_checks`: `{"doc_type", "checked_at"}` moves the check date of a document the object already has; its status
  is not touched, so the legal basis of today stays the same.
- `complaint_verifications`: `{"external_id", "verified_at"}` moves the verification time of a verified complaint the
  object already has.

After the facts are loaded, the ads of these objects are analysed (the dictionary hits are what R2 reads) and
`replay_history` runs the risk engine for every new demo object over the last 26 weeks, weekly, at UTC midnight:
`risk_score` rows with `trigger=replay`. Nothing is painted by hand. Stage and readiness are the current ones: there is
no history of them (OPEN_QUESTIONS 34). The story of the three control scenarios:

| Object | Replayed zones, oldest to newest |
|---|---|
| ЖК «Золотая осень» (B) | green, yellow once a paid booking shows up, red once both legal-basis checks are on record |
| ЖК «Северный бриз» (A) | green, then yellow for 14 weeks (bookings, basis never checked) |
| ЖК «Тихая гавань» (C) | green, a month of yellow while an installment ad ran, green again |

`python -m app.seed --replay-history` recomputes the replayed history of every object in the database (also the real
ones), in the same way; the demo seed does it by itself for new demo objects.

## `demo_activity.json`, `demo_vision.json`, `demo_flight_*.mp4` (only with `--demo`)

The living demo around the objects above: what the integrations would have produced if every one of them were on.
Nothing is collected from the internet. Read by `app/seed_activity.py` and `app/seed_vision.py`, loaded last, every piece
idempotent on its own (a repeated run adds nothing). Same fictional-data rules (URLs `example.invalid`, phones
`+7 700 000 ...`, `is_demo=true`).

`demo_activity.json`:

- `sources`: 19 `SourceAccount` of every platform (Telegram channels and a group, Instagram, TikTok, sites, krisha- and
  OLX-like search pages, a forum), bound to an object, a developer or neither. Each has hand-written `posts` and a `feed`
  that expands the text `pools` into dozens of publications over 1 to 110 days (origin `collector`). The pools hold risky
  wordings that the dictionary matches, ordinary texts, Kazakh texts (the dictionary is Russian: only the model's
  findings read them), OCR snippets and triage notes. A test checks that every risky template is matched and no ordinary
  one is. The pipeline is reproduced: screenshots (synthetic, `seed_media.py`), OCR text after `[OCR]`, hypotheses of the
  LLM (`llm_extraction`, `llm_status=done`, LLM hits that wait for a person), later versions of edited texts, posts found
  removed, dictionary hits confirmed or rejected, triage states (`reviewed`, `deferred`, `irrelevant`). Publications that
  staff would have confirmed are older than the analysis window, so no score changes; the recent ones wait in the
  queue (`status=verification`) except those of a source bound to a red object or to the object with ordinary texts.
- `citizen_reports`, `pools.citizen`: publications sent through the bot, created with `submit_citizen_report` (the officers
  of the city are notified). `bot_complaints`: complaints through `submit_complaint`. `complaints` and `complaints_per_object`:
  E-Otinish, manual and other complaints in every status, some verified, several collective (none is both verified and
  open: R4 would move a score).
- Older inspections with photos (two per object, before the one the object has), `registry_response` evidence for the
  documents confirmed by the housing portal and the record of the last registry sync, websites, sales offices, advertising
  accounts and one bank detail shared by two developers (graph edges).
- `signals`: cards in every status, made with the functions of the signals module (so the audit trail and the notifications
  are real), the three automatic drafts of the red objects included; `assignments`: open, done, cancelled, some overdue.
  `seed_activity` scores the new objects itself before it builds cards.

**Demo sources are never polled.** Every demo source has `is_watched=false`: the collectors (`collect.run_all`) and the
Telegram userbot read only watched sources, so a demo source is not joined, not fetched and never gets a `last_error`.
Watching one by hand in the UI would make the live collectors try its fictional address.

`demo_vision.json`: seven SAQ VISION sessions (drone, camera, phone) with photos and two real MP4 videos
(`demo_flight_crystal.mp4`, `demo_flight_riviera.mp4`, 10 s, about 100 KB each), frames, completed detector runs, raw
detections, findings in every review state and the publications made from outdoor advertising (origin `vision`). The media
is synthetic: `app/seed_media.py` draws a stylized site (crane, fence, billboard with the banner) with Pillow; the videos
were assembled from such frames with ffmpeg (the command is in that module). Originals and previews are stored through
`storage.put_vision_object`; no job is queued, the GPU worker is not needed.

## `pilot/ust-kamenogorsk-public-2026-10-13.json` (only with `--pilot`, optional)

A snapshot of public data collected on 2026-10-13 (third-party data, not verified by SAQ): 26 residential complexes
under construction from the krisha.kz catalogue (`objects`) and 15 records of the register of shared construction
objects of АО «КЖК» (`homeportal_registry_objects_vko`). Ships in the backend image (the build context is `backend/`).
The import is described in `app/modules/registry_sync/pilot.py`; in short:

- Real objects are `is_demo=false` and carry only facts of the snapshot. **Legal entities only** (SPEC D19): a developer
  gets the BIN and legal name of the registry; no director, founders, phone or e-mail is imported. No complaints, no
  ads, no `prior_violations`: the zone is calculated by the risk module.
- Union: every krisha.kz object, plus every registry record no krisha.kz object claims, except records the portal counts
  as completed (commissioning date in the past): Tumar Towers (1077) is skipped. A registry-only record with
  coordinates outside the city (Renesans, 1428) is imported without a position.
- A registry match is trusted unless the snapshot itself says «не подтверждено» and krisha.kz does not show the same
  document number. Such a match (Satti City 2 vs registry «Satti City») is not linked: the registry record becomes an
  object of its own and the krisha.kz object gets the placeholder document, both cross-referencing in their notes.
- Documents: «Разрешение МИО» / «Участие БВУ» -> `dsu_permit`, «Гарантия КЖК» -> `guarantee`; number and issue date
  from the registry, `check_status=confirmed`, `check_source=housing_portal`, `checked_at` = collection date,
  the registry URL in the note. Several records of one object (ЖАНЫМ: guarantee and two amendments) make several
  documents. A krisha.kz object without a registry record gets one `dsu_permit` in status `checking` with the note
  «требуется ручная сверка: в выгрузке реестра КЖК от 2026-10-13 не найден» and what krisha.kz states.
- Position, address and cadastral number come from the registry when its point lies within 500 m of the krisha.kz
  point; otherwise (Asyl Tau, 1.6 km) the krisha.kz position is kept and the note says so. Planned completion is the
  latest commissioning date of the registry records, else the end of the krisha.kz quarter; the forecast equals it.
  Status is `active`, or `not_started` when the registry start date is in the future.
- BINs from third-party aggregators (statsnet.co) are not entered into the developer card (the model has no field
  for «не проверено»); the BIN and its source are quoted in the note of the object's `checking` document.
- District: point in polygon (PostGIS `ST_Contains`) against `districts.geojson`.
- Repeatable: objects are found again by document number, cadastral number, developer and site, or name. An existing
  object is only completed (empty fields filled), never overwritten; a document checked by a person is left alone.

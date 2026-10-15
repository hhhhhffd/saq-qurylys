# SAQ QURYLYS

Risk monitoring of residential construction objects. The binding contract is [docs/SPEC.md](docs/SPEC.md).

## Dev quickstart

Requirements: Docker with Compose v2, [uv](https://docs.astral.sh/uv/) for running the backend on the host.

```bash
cp .env.example .env          # dev-only placeholder values; never commit .env
docker compose up -d --build db redis minio api worker beat   # add `frontend` once ./frontend exists
docker compose exec api python -m app.seed          # reference data + initial admin (idempotent)
docker compose exec api python -m app.seed --demo   # + demo users and demo objects (prints demo passwords once)
curl localhost:8000/api/v1/health
curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"admin","password":"change-me-admin-password"}'
```

| Service | Host port | Notes |
|---|---|---|
| api | 8000 | OpenAPI at `/docs`; runs `alembic upgrade head` on start |
| frontend | 8080 | nginx, proxies `/api` to `api:8000` |
| db | 5433 | PostgreSQL 16 + PostGIS (`POSTGRES_*` in `.env`) |
| redis | 6379 | Celery broker |
| minio | 9000 / 9001 | S3 API / console. The evidence bucket is created with Object Lock by the backend at startup |

`JWT_SECRET` is required (at least 32 characters; `openssl rand -hex 32`). The API refuses to start without it.

### Backend on the host

```bash
cd backend
uv sync
uv run alembic upgrade head          # uses DATABASE_URL from ../.env
uv run uvicorn app.main:app --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
uv run pytest                        # needs `docker compose up -d db redis minio`
```

Tests create a separate `saq_test` database, run the Alembic migrations in it and use a real MinIO bucket
(`evidence-test`). Override with `TEST_DATABASE_URL`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.
Every test runs in a rolled-back transaction. The Celery hook `app.events.object_changed` is disabled in tests
(`EVENTS_ENABLED=false`).

## Celery contract

Queues: `collect`, `archive`, `nlp`, `score`, `notify`, `default`. Tasks are implemented in each module's
`app/modules/<module>/tasks.py` (auto-discovered) under these exact names:

| Task | Queue | Schedule (UTC) |
|---|---|---|
| `archive.capture` | archive | on demand |
| `nlp.analyze`, `nlp.link`, `nlp.llm_extract` | nlp | on demand |
| `risk.recalc_object(object_id)` | score | on demand, via `app.events.object_changed(object_id)` |
| `risk.sweep_due` | score | daily 02:00 |
| `collect.run_all` | collect | daily 01:00 |
| `ads.recheck_due` | collect | every 6 hours |
| `signals.check_deadlines` | notify | daily 06:00 |
| `notify.red_zone` | notify | on demand |

Call `object_changed(object_id)` **after** committing a change to an object, its documents, complaints,
inspections or ads. It is a no-op when `EVENTS_ENABLED=false`.

## CSV import

Both importers accept UTF-8 (or Windows-1251) files with a header row and `,`, `;` or tab as separator.
Column names are case-insensitive; unknown columns are ignored. Dates are `YYYY-MM-DD` or `DD.MM.YYYY`;
decimals may use `.` or `,`; booleans are `1/0`, `true/false`, `yes/no`, `да/нет`. Valid rows are saved even
if other rows fail. The response is `{"created": N, "updated": N, "errors": [{"row": N, "message": "..."}]}`
where `row` is the spreadsheet row number (the header is row 1).

### `POST /api/v1/objects/import`

| Column | Required | Description |
|---|---|---|
| `name` | yes | Object name |
| `territory_code` | yes | Code of a city territory you can access, e.g. `ust-kamenogorsk` |
| `code` | no | Existing object code (`SQ-OBJ-0001`): updates that object. An unknown code is an error |
| `district` | no | District name within the city |
| `developer_bin` | no | 12-digit BIN. If unknown, `developer_name` creates the developer |
| `developer_name` | no | Used only to create a new developer |
| `aliases` | no | Alternative names separated by `\|` (replaces the current list) |
| `address`, `cadastral_number`, `land_purpose`, `prior_violations` | no | Text |
| `lat`, `lon` | no | WGS84; both or neither |
| `planned_completion`, `forecast_completion`, `stalled_since` | no | Dates |
| `construction_status` | no | `not_started`, `active` (default on create), `stalled`, `completed` |

Without `code`, an existing object is matched by `cadastral_number`, otherwise by city + name + address,
so re-importing the same file updates instead of duplicating. Empty cells leave existing values unchanged.

### `POST /api/v1/complaints/import`

| Column | Required | Description |
|---|---|---|
| `object_code` | yes | Object code, e.g. `SQ-OBJ-0001` |
| `received_at` | yes | Date received |
| `source` | no | `eotinish` (default), `manual`, `other` |
| `external_id` | no | Complaint number in the source system. `(source, external_id)` identifies a complaint: a repeat updates it |
| `is_collective`, `confirmed_payments` | no | Booleans (default no) |
| `signatories_count` | no | Integer >= 1 (default 1) |
| `summary` | no | Text |
| `status` | no | `new` (default), `in_review`, `closed` |

## Seed data files

Optional files in `backend/app/seed_data/` (districts, holidays, demo objects) are loaded by `python -m app.seed`.
Their formats are in [backend/app/seed_data/README.md](backend/app/seed_data/README.md).

## Notes

- Upstream MinIO no longer publishes official Docker images. Compose pins a community build of the last upstream
  release (`alpine/minio`). The backend uses only the S3 API with Object Lock, so another S3-compatible store
  with Object Lock can be used by changing `S3_*` in `.env`.
- Evidence is immutable by design: `evidence`, `audit_log` and `risk_factor_change` reject UPDATE, DELETE and
  TRUNCATE through database triggers.

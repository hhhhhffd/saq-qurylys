# SAQ QURYLYS — спецификация реализации (контракт)

Источник требований: ТЗ (оригинал) + решения, принятые с заказчиком 13.10.2026 (раздел 1).
Этот документ — контракт между backend, frontend и воркерами. Изменения контракта вносятся сюда.

## 1. Принятые решения

| # | Решение |
|---|---------|
| D1 | Объём v1: все модули ТЗ, кроме автоматических парсеров соцсетей. Парсеры — фаза 2 (интерфейс коллектора закладывается в v1). Запуск локально через `docker compose`; на проде предполагается Cloudflare Tunnel перед nginx — в разработке не используется. |
| D2 | Полный стек сразу (масштаб на всю РК): FastAPI + Celery + Redis + PostgreSQL 16/PostGIS + MinIO (Object Lock) + React. |
| D3 | Госреестры (Жилищный портал, Казреестр, кадастр, e-Otinish) — ручная сверка со скриншотом-доказательством; обращения — ручной ввод + импорт CSV. |
| D4 | Данные пилота: публичные, если удаётся достать; иначе мок-данные (`is_demo=true`) + инструкция `docs/DATA_SOURCES.md`, где и как их получить. |
| D5 | Стартовые веса факторов — из оригинала ТЗ; админ меняет, история изменений ведётся. Зона — по правилам (раздел 6), балл — для сортировки и расшифровки. |
| D6 | ИИ: словарь формулировок (детерминированно, влияет на балл) + LLM через Ollama (`qwen3.5:9b-q6k`), результат LLM = «предположение ИИ», на балл влияет только после подтверждения человеком. Без Ollama система работает. |
| D7 | Собственный JWT + RBAC (роли: `admin`, `mio_officer`, `gask`, `law_enforcement`). |
| D8 | Уведомления in-app; SMTP опционально. Срок рассмотрения — N рабочих дней (по умолчанию 5) с учётом производственного календаря РК (таблица `holiday`). |
| D9 | i18n: `ru` (основной) и `kk`. Backend отдаёт коды (статусы, факторы, ошибки), тексты переводит frontend. |
| D10 | Территории двухуровневые: область (`region`) → город (`city`); внутри города — районы (`district`) для фильтра. Пользователь привязан к территории (или `null` = вся РК) и видит её и всё, что ниже. |
| D11 | MinIO Object Lock: режим и срок из `.env` (`EVIDENCE_LOCK_MODE=GOVERNANCE`, `EVIDENCE_RETENTION_DAYS=1` в dev; `COMPLIANCE` и 1825 на проде). |
| D12 | RFC 3161 метка времени: реализована, выключена по умолчанию (`TSA_URL` пустой). Наружу уходит только sha256. |
| D13 | «Зафиксировать по ссылке» — в v1: воркер открывает URL в Playwright, сохраняет полностраничный PNG и MHTML (CDP `Page.captureSnapshot`). |
| D14 | Публичной части нет — только внутренний вход. |
| D15 | Ollama: в разработке на хосте (`ollama serve`), настройки `LLM_ENABLED`, `OLLAMA_URL`, `OLLAMA_MODEL`, `LLM_TIMEOUT_S`. |
| D16 | UI: одна тема, нейтральная средняя палитра (не тёмная и не ослепительно-белая), минимализм в духе Apple. Цвета зон — единственные насыщенные акценты. Во всех экранах/выгрузках с зоной — дисклеймер «Красная зона означает высокий риск и необходимость проверки, а не установленную виновность». Без госсимволики. |

## 2. Структура репозитория

```
backend/            Python 3.12, uv, FastAPI, SQLAlchemy 2 (sync, psycopg 3), Alembic, Celery
  app/
    main.py config.py db.py security.py deps.py
    models/         все ORM-модели
    modules/<name>/ router.py service.py schemas.py tasks.py (по модулям)
    worker/celery_app.py
    collectors/     интерфейс коллектора (фаза 2 — реализации)
    templates/      Jinja2 (PDF сигнальной карточки)
  alembic/  tests/  pyproject.toml  Dockerfile
frontend/           React + TypeScript + Vite, pnpm
docker-compose.yml  .env.example  docs/
```

Сервисы compose: `db` (postgis/postgis:16), `redis`, `minio` (+ одноразовый `minio-init` не нужен — бакет с object lock создаёт backend при старте), `api`, `worker` (Celery, образ с Playwright Chromium), `beat`, `frontend` (dev: vite; prod: nginx со статикой и прокси `/api`).

API: префикс `/api/v1`, JSON, даты ISO 8601 (UTC в БД, отображение в часовом поясе территории). Ошибки: `{"detail": {"code": "<snake_case>", "message": "<ru>"}}`. Пагинация списков: `?limit=&offset=` → `{"items": [...], "total": N}`.

## 3. Модель данных

Все таблицы имеют `id` (bigint identity), `created_at`, `updated_at` (кроме append-only).

- **territory**: `parent_id`, `level` (`region|city`), `code` (уник.), `name`, `timezone`, `center` (Point 4326), `boundary` (MultiPolygon 4326, nullable).
- **district**: `territory_id` (city), `name`, `boundary` (MultiPolygon).
- **app_user**: `username` (уник.), `full_name`, `password_hash` (argon2), `role`, `territory_id` (nullable = вся РК), `is_active`, `locale` (`ru|kk`).
- **developer**: `bin` (12 цифр, уник.), `name`, `director`, `founders` (jsonb list[str]), `authorized_company`, `phones` (text[]).
- **construction_object**: `code` (`SQ-OBJ-NNNN`, из sequence), `territory_id` (city), `district_id`, `developer_id`, `name`, `aliases` (text[]), `address`, `cadastral_number`, `land_purpose`, `location` (Point 4326), `planned_completion` (date), `forecast_completion` (date), `construction_status` (`not_started|active|stalled|completed`), `stalled_since` (date), `readiness_actual_pct` (из последней фотофиксации), `readiness_claimed_pct` (из подтверждённой рекламы), `prior_violations` (text), `score` (int), `zone` (`green|yellow|red`, nullable до первого расчёта), `key_status` (код, см. 6.4), `last_scored_at`, `next_check_at`, `is_demo`.
- **document**: `object_id`, `doc_type` (`smr_notice|psd|expertise|dsu_permit|guarantee|ddu_registration|land_title`), `number`, `issued_at`, `issuer`, `check_status` (`confirmed|not_found|checking`), `checked_at`, `checked_by`, `check_source` (`housing_portal|kazreestr|mio_registry|cadastre|eotinish|manual|other`), `note`.
- **inspection** (фотофиксация): `object_id`, `inspected_at` (date), `readiness_pct`, `location` (Point, nullable), `inspector_id`, `note`.
- **complaint**: `object_id`, `received_at`, `source` (`eotinish|manual|other`), `external_id`, `is_collective`, `signatories_count`, `summary`, `status` (`new|in_review|closed`), `confirmed_payments` (bool — заявитель подтвердил платёж застройщику).
- **linked_entity**: `object_id` | `developer_id`, `kind` (`ad_account|sales_office|phone|website|bank_details`), `value`, `note`.
- **source_account**: `platform` (`instagram|tiktok|telegram|website|aggregator|outdoor|other`), `handle`, `url`, `object_id`, `developer_id`, `territory_id`, `is_watched`, `last_collected_at`.
- **ad_post**: `territory_id`, `source_account_id`, `platform`, `url`, `external_id` (уник. с platform), `author`, `published_at`, `captured_at`, `text`, `phones` (text[], E.164), `links` (text[]), `object_id`, `link_confidence` (0..1), `link_method` (`account|phone|name|manual`), `payment_schemes` (text[] из `booking|down_payment|deposit|installment|nonstandard_contract`; подтверждённые), `claimed_readiness_pct`, `price_before_completion` (bool), `llm_extraction` (jsonb), `llm_status` (`none|pending|done|failed|disabled`), `status` (`captured|verification|removed_saved`), `max_phrase_weight`, `total_phrase_weight`, `is_outdoor`, `location` (Point, для наружной), `last_checked_at`, `removed_detected_at`, `capture_status` (`pending|done|failed`), `capture_error`.
- **evidence** (append-only, UPDATE/DELETE запрещены триггером): `kind` (`screenshot_png|archive_mhtml|photo|document_scan|pdf`), `bucket`, `s3_key`, `sha256`, `size_bytes`, `content_type`, `captured_at` (время сервера), `source_url`, `retention_until`, `lock_mode`, `tsa_token` (bytea, nullable), `ad_post_id` | `document_id` | `inspection_id` | `signal_card_id` (ровно одно не null), `created_by`.
- **phrase**: `text`, `variants` (text[]), `category` (`booking|down_payment|installment|sales_start|preliminary_contract|deposit|price_before_completion|covert_contract`), `weight` (int), `is_active`.
- **phrase_hit**: `ad_post_id`, `phrase_id` (nullable для LLM), `category`, `matched_text`, `start`, `end` (символьные позиции в `ad_post.text`), `weight`, `detected_by` (`dictionary|llm`), `confirmed` (bool nullable), `confirmed_by`.
- **risk_factor**: `code` (PK), `description`, `weight` (int, может быть отрицательным), `is_active`, `sort_order`.
- **risk_factor_change** (append-only): `code`, `old_weight`, `new_weight`, `old_active`, `new_active`, `changed_by`, `changed_at`.
- **risk_score** (история): `object_id`, `score`, `zone`, `zone_reasons` (text[] кодов), `breakdown` (jsonb, см. 6.3), `trigger` (`event|schedule|manual`), `calculated_at`.
- **signal_card**: `number` (`SQ-ГГГГ-NNNN`, счётчик по году в таблице `signal_counter`), `object_id`, `status` (`requires_confirmation|returned|sent|responded|closed`), `origin` (`auto|manual`), `sections` (jsonb, см. 7.1), `recipient` (`mio|gask|law_enforcement`), `review_days`, `sent_at`, `sent_by`, `due_date`, `return_comment`, `response_text`, `response_at`, `responded_by`, `created_by`.
- **audit_log** (append-only): `user_id`, `at`, `action`, `entity_type`, `entity_id`, `before` (jsonb), `after` (jsonb), `ip`.
- **notification**: `user_id`, `kind` (`red_zone|signal_returned|signal_sent|signal_due_soon|signal_overdue|signal_responded|capture_failed`), `entity_type`, `entity_id`, `payload` (jsonb), `created_at`, `read_at`.
- **holiday**: `day` (PK date), `kind` (`holiday|workday` — `workday` = перенесённый рабочий выходной), `name`.
- **app_setting**: `key` (PK), `value` (jsonb). Ключи и умолчания: `review_days=5`, `ad_window_days=7`, `readiness_gap_pp=10`, `complaints_threshold=3`, `stalled_days=30`, `recheck_after_days=3`, `link_confidence_threshold=0.8`, `green_interval_days=30`, `yellow_interval_days=7`.

## 4. Роли и доступ

| Действие | admin | mio_officer | gask | law_enforcement |
|---|---|---|---|---|
| Дашборд, объекты, реклама (чтение) | ✓ | ✓ | — | — |
| CRUD объектов, документов, обращений, фотофиксации, рекламы, «зафиксировать по ссылке» | ✓ | ✓ | — | — |
| Подтверждение фраз/схем оплаты/связей рекламы | ✓ | ✓ | — | — |
| Сигнальные карточки: создать, редактировать, «Подтвердить и направить», «Вернуть на доработку» | — (только чтение) | ✓ | — | — |
| Сигнальные карточки, направленные этому органу: чтение, внести результат | — | — | ✓ (recipient=gask) | ✓ (recipient=law_enforcement) |
| Пользователи, территории, словарь, веса, календарь, настройки | ✓ | — | — | — |
| Журнал действий | ✓ | ✓ (по своим карточкам) | — | — |

Все данные фильтруются по территории пользователя (его территория и дочерние). Отправка во внешние органы — только эндпоинт `confirm-and-send`, вызываемый пользователем с ролью `mio_officer`; ни одна задача Celery не меняет статус на `sent`.

## 5. Мониторинг рекламы и ИИ

Пайплайн для каждой новой публикации (Celery-цепочка): `archive.capture` (если есть URL) → `nlp.analyze` → `nlp.link` → `nlp.llm_extract` (если `LLM_ENABLED`) → `risk.recalc_object` (если есть `object_id`).

- **Словарь**: совпадение по последовательности лемм (pymorphy3) для `text` и каждого из `variants`. Совпадение сохраняется как `phrase_hit` с позициями исходного текста. Стартовый словарь — 9 формулировок из ТЗ с вариантами (например, «бронирование» → `бронь`, `забронировать`, `бронирование`).
- **Телефоны**: `phonenumbers`, регион `KZ`, формат E.164.
- **Связывание с объектом**, по приоритету: аккаунт привязан к объекту → совпал телефон из `linked_entity`/`developer.phones` → нечёткое совпадение названия или алиаса (rapidfuzz `token_set_ratio`/100). Если `link_confidence < link_confidence_threshold` или кандидатов несколько, статус `verification`.
- **LLM**: Ollama `/api/chat` со structured output (`format` — JSON-схема `{payment_schemes: [...], claimed_readiness_pct: int|null, price_before_completion: bool, quotes: [str]}`); результат пишется в `llm_extraction` и как `phrase_hit` с `detected_by=llm, confirmed=null`. В `payment_schemes`/`claimed_readiness_pct` поста он попадает только после подтверждения пользователем.
- **Перепроверка**: через `recheck_after_days` воркер проверяет URL (HTTP-статус и признаки удаления). Если публикация удалена, статус `removed_saved`; доказательства не трогаются.
- **Наружная реклама**: ручной ввод (текст, фото, геоточка, `is_outdoor=true`).
- **Коллекторы (фаза 2)**: `collectors/base.py`: `class Collector(Protocol): platform; def collect(account: SourceAccount, since: datetime) -> Iterable[CollectedPost]`. Реестр коллекторов по `platform`; задача `collect.run_all` (beat, ежедневно) для v1 зарегистрирована, но при отсутствии реализаций ничего не делает и пишет это в лог.

## 6. Оценка риска

### 6.1. Факторы (стартовые веса — из оригинала ТЗ)

| code | Условие срабатывания | Вес |
|---|---|---|
| `no_permit` | нет `document` типа `dsu_permit` или `guarantee` со статусом `confirmed` | +40 |
| `money_offer` | за `ad_window_days` есть подтверждённая (или словарная) формулировка категорий `booking|down_payment|deposit|installment|preliminary_contract|covert_contract|price_before_completion` либо подтверждённая `payment_schemes` | +20 |
| `active_ads` | за `ad_window_days` есть хотя бы одна публикация, связанная с объектом | +15 |
| `complaints` | есть обращение с `is_collective=true` или открытых обращений ≥ `complaints_threshold` | +15 |
| `readiness_overstated` | `readiness_claimed_pct − readiness_actual_pct ≥ readiness_gap_pp` | +10 |
| `on_schedule` | `construction_status=active`, `forecast_completion ≤ planned_completion` и последняя фотофиксация не старше `stalled_days` | −15 |

Балл = сумма весов активных сработавших факторов, обрезанная до [0; 100].

### 6.2. Правила зон (зона по правилам, а не по порогу балла)

Вспомогательные признаки: `permit_confirmed` (есть подтверждённое разрешение или гарантия), `permit_checking` (разрешение/гарантия в статусе `checking`), `money_offer`, `covert_contract` (формулировка категории `covert_contract`/`preliminary_contract` или схема `nonstandard_contract`), `confirmed_payments` (обращение с `confirmed_payments=true`), `overdue` (`forecast_completion > planned_completion` или `planned_completion < сегодня` и не `completed`), `stalled` (`construction_status=stalled`), `complaints`, `readiness_overstated`, `active_ads`.

- **red**: `not permit_confirmed and not permit_checking and (money_offer or covert_contract or confirmed_payments)`.
- **green**: `permit_confirmed and not (overdue or stalled or complaints or readiness_overstated)`.
- **yellow**: всё остальное (в том числе разрешение на проверке, реклама без предложения денег, отсутствие разрешения без рекламы).

`zone_reasons` — коды сработавших условий правила.

### 6.3. Расшифровка (`risk_score.breakdown`)

```json
[{"code": "no_permit", "weight": 40, "triggered": true,
  "evidence": [{"type": "document", "id": 12}, {"type": "ad_post", "id": 55}],
  "detail": {"...": "..."}}]
```

В расшифровку попадают все активные факторы, в том числе несработавшие (`triggered=false`, вес не суммируется).

### 6.4. `key_status` объекта (для дашборда)

Первый сработавший код по приоритету: `no_permit_with_offer`, `no_permit`, `permit_checking`, `money_offer`, `stalled` (с `stalled_days` в detail, UI показывает «простой N дней»), `overdue`, `complaints`, `readiness_overstated`, `ok`.

### 6.5. Расписание пересчёта

- По событию (новая или изменённая публикация, документ, обращение, фотофиксация, подтверждение фразы, изменение весов) — немедленно, `trigger=event`.
- Beat ежедневно в 02:00 (время территории не важно, берётся UTC): `risk.sweep_due` пересчитывает объекты с `next_check_at ≤ now`. После расчёта `next_check_at` = now + 7 дней для yellow, + 30 для green, + 1 день для red.
- Переход в red (или первый расчёт red): уведомление `red_zone` всем `mio_officer` территории и черновик сигнальной карточки (`origin=auto`), если у объекта нет карточки в статусах `requires_confirmation|returned|sent`.

## 7. Сигнальная карточка

### 7.1. `sections` (jsonb)

```
object_developer: {object_code, object_name, address, cadastral_number, land_purpose,
                   developer_name, bin, director, founders[]}
risk_factors:     [{code, weight, detail}]            -- копия сработавших факторов на момент формирования
permit_checks:    [{doc_type, source, check_status, checked_at, number, evidence_ids[]}]
publications:     [{ad_post_id, platform, url, published_at, captured_at, evidence_ids[], status}]
scheme_payments:  {payment_schemes[], contract_types[], confirmed_payments_note}
proposed_measures:[код из request_documents|site_inspection|interview_complainants|request_payments_info]
route:            {recipient, review_days}
note:             str                                  -- свободный комментарий сотрудника
```

### 7.2. Жизненный цикл

`requires_confirmation` → (`mio_officer`: «Вернуть на доработку», нужен комментарий) → `returned` → (правка) → `requires_confirmation`
`requires_confirmation` → (`mio_officer`: «Подтвердить и направить», нужен `recipient`) → `sent` (`sent_at`, `due_date` = `sent_at` + `review_days` рабочих дней по календарю) → (получатель вносит результат) → `responded` → (`mio_officer` закрывает) → `closed`.

Каждый переход и правка записываются в `audit_log`. Beat ежедневно (`signals.check_deadlines`): уведомление `signal_due_soon` за 1 рабочий день до срока и `signal_overdue` в день просрочки, получатели — `mio_officer` территории и пользователи-получатели. Карточка в статусе `sent` с прошедшим `due_date` отдаётся с `is_overdue=true`.

PDF: WeasyPrint, Jinja2-шаблон `templates/signal_card.html`; в PDF встраиваются PNG-снимки доказательств, в шапке и подвале — дисклеймер про красную зону. Если `SMTP_HOST` задан, после подтверждения отправляется письмо с PDF на адрес органа из настройки `recipient_emails` (`app_setting`).

## 8. API (`/api/v1`)

Auth
- `POST /auth/login` `{username, password}` → `{access_token, token_type:"bearer", user}`
- `GET /auth/me` → `User {id, username, full_name, role, territory_id, locale}`

Справочники
- `GET /territories` (дерево, доступное пользователю) · `POST/PATCH /territories` (admin)
- `GET /territories/{id}/districts` → GeoJSON FeatureCollection
- `GET/POST /users`, `PATCH /users/{id}` (admin)
- `GET/PUT /settings` (admin; GET доступен и mio_officer)
- `GET/POST /holidays`, `DELETE /holidays/{day}` (admin)

Дашборд
- `GET /dashboard?territory_id=&district_id=` → `{counts:{green,yellow,red,unscored,total}, last_updated_at, objects:[ObjectRow]}`
  `ObjectRow = {id, code, name, developer_name, score, zone, key_status, key_status_detail, district_name, lat, lon}`, сортировка по убыванию балла.

Реестр
- `GET /objects?zone=&district_id=&q=&limit=&offset=` → `{items:[ObjectRow], total}`
- `POST /objects` · `PATCH /objects/{id}` · `GET /objects/{id}` → `ObjectDetail` (паспорт + `developer` + `documents` + `inspections` + `complaints` + `linked_entities` + `ads_7d_count` + `readiness_gap_pp` + `latest_score{score, zone, zone_reasons, breakdown, calculated_at}`)
- `GET /objects/{id}/score-history` · `POST /objects/{id}/recalculate`
- `POST /objects/import` (CSV, multipart) → `{created, updated, errors:[{row, message}]}`
- `GET/POST /developers`, `PATCH /developers/{id}`
- `POST /objects/{id}/documents` (multipart: поля + опциональный `file` → evidence `document_scan`) · `PATCH /documents/{id}`
- `POST /objects/{id}/inspections` (multipart: поля + `photos[]` → evidence `photo`)
- `POST /objects/{id}/complaints` · `PATCH /complaints/{id}` · `POST /complaints/import` (CSV)
- `POST /objects/{id}/linked-entities` · `DELETE /linked-entities/{id}`

Реклама
- `GET /ads?platform=&object_id=&status=&q=&limit=&offset=` (сортировка: `max_phrase_weight desc, published_at desc`) → `{items:[AdRow], total}`
- `GET /ads/{id}` → `AdDetail` (+ `phrase_hits`, `evidence`, `llm_extraction`, `linked_object`)
- `POST /ads/capture` `{url, object_id?, platform?}` → `AdDetail` (`capture_status=pending`)
- `POST /ads/manual` (multipart: text, platform, url?, object_id?, published_at, is_outdoor, lat, lon, photos[])
- `PATCH /ads/{id}` `{object_id?, status?, payment_schemes?, claimed_readiness_pct?, price_before_completion?}`
- `POST /ads/{id}/hits/{hit_id}/confirm` `{confirmed: bool}`
- `POST /ads/{id}/accept-llm` — перенести извлечённое LLM в подтверждённые поля
- `GET/POST /source-accounts`, `PATCH /source-accounts/{id}`
- `GET/POST /phrases`, `PATCH /phrases/{id}` (admin)

Риск
- `GET /risk-factors` · `PATCH /risk-factors/{code}` `{weight?, is_active?, description?}` (admin) · `GET /risk-factors/history`

Доказательства
- `GET /evidence/{id}` → метаданные · `GET /evidence/{id}/content` → поток файла (проверка доступа)

Сигнальные карточки
- `GET /signals?status=&object_id=` → `{items:[SignalRow{id, number, object_id, object_name, zone, status, recipient, due_date, is_overdue, created_at}], total}`
- `POST /signals` `{object_id}` (ручное формирование)
- `GET /signals/{id}` → `SignalDetail` (+ `sections`, `audit`)
- `PATCH /signals/{id}` `{sections?, recipient?, review_days?}` (только в `requires_confirmation|returned`)
- `POST /signals/{id}/confirm-and-send` `{recipient}` · `POST /signals/{id}/return` `{comment}` · `POST /signals/{id}/response` `{response_text}` · `POST /signals/{id}/close`
- `GET /signals/{id}/pdf`

Прочее
- `GET /notifications?unread=true` · `POST /notifications/{id}/read` · `POST /notifications/read-all`
- `GET /audit?entity_type=&entity_id=` · `GET /health`

## 9. Конфигурация (`.env`)

`DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_EVIDENCE`, `EVIDENCE_LOCK_MODE`, `EVIDENCE_RETENTION_DAYS`, `TSA_URL`, `JWT_SECRET`, `JWT_TTL_MINUTES`, `LLM_ENABLED`, `OLLAMA_URL`, `OLLAMA_MODEL=qwen3.5:9b-q6k`, `LLM_TIMEOUT_S`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `CORS_ORIGINS`, `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`. Секреты — только в `.env` (в git не попадает), в репозитории только `.env.example`.

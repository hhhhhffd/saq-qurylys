# SAQ QURYLYS — спецификация реализации (контракт)

Источник требований: ТЗ (оригинал) + **кейс Codemasters 8.0 «SAQ QURYLYS» (приоритетный источник при расхождениях)** + решения, принятые с заказчиком 13.10.2026 (раздел 1).
Этот документ — контракт между backend, frontend и воркерами. Изменения контракта вносятся сюда.

## 1. Принятые решения

| # | Решение |
|---|---------|
| D1 | Объём v1: все модули ТЗ, кроме автоматических парсеров соцсетей. Парсеры — фаза 2 (раздел 10). Запуск локально через `docker compose`; на проде предполагается Cloudflare Tunnel перед nginx — в разработке не используется. |
| D2 | Полный стек сразу (масштаб на всю РК): FastAPI + Celery + Redis + PostgreSQL 16/PostGIS + MinIO (Object Lock) + React. |
| D3 | Госреестры (Жилищный портал, Казреестр, кадастр, e-Otinish) — ручная сверка со скриншотом-доказательством; обращения — ручной ввод + импорт CSV. |
| D4 | Данные пилота: публичные, если удаётся достать; иначе мок-данные (`is_demo=true`) + инструкция `docs/DATA_SOURCES.md`, где и как их получить. |
| D5 | ~~Веса из оригинала ТЗ, зона по правилам~~ — заменено D17. Админ меняет веса, история изменений ведётся. |
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
| D16 | UI: одна тёмная тема в стиле Fatality (индиго, розовый акцент) на Tailwind v4 + shadcn/ui — решение от 13.10.2026, контракт в [docs/UI.md](UI.md); красная зона всегда отличима от розового акцента и подписана словом. Во всех экранах/выгрузках с зоной — дисклеймер «Красная зона означает высокий риск и необходимость проверки, а не установленную виновность». Без госсимволики. |
| D17 | Модель риска — из кейса Codemasters 8.0 (раздел 6): факторы R1–R6, балл = min(100, Σ весов подтверждённых факторов), зона по баллу с условием R1+R2 для красной. «Нет данных» ≠ «нет основания»: неизвестные сведения дают 0 баллов и помечаются «Нужна проверка». Гипотезы ИИ не считаются подтверждёнными фактами. Обязательные тест-сценарии A/B/C (6.6) покрыты автотестами и демо-данными. |
| D18 | Достоверность: в UI и PDF явно различаются «факт» (подтверждённые данные с источником и временем фиксации), «гипотеза ИИ» (с фрагментом и уверенностью, принять/отклонить) и «демо» (`is_demo` у объектов и публикаций; бейдж «ДЕМО» в интерфейсе, водяной знак в PDF). |
| D19 | Демо-данные: только вымышленные ЖК/застройщики/люди, ≥ 8 полных карточек ЖК, ≥ 12 публикаций, сценарии A/B/C. Реальные публичные данные (`--pilot`) — только факты о юрлицах из реестров, без ФИО и контактов физлиц, без каких-либо оценок; в демо по умолчанию не загружаются. |
| D20 | Сдача — публичный репозиторий GitHub (отсечка 20.10.2026 23:59): README по структуре кейса (проблема и ценность, возможности, технологии, архитектура, запуск, тестовый сценарий, ограничения, использование ИИ, сторонние библиотеки и модели). |

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
- **complaint**: `object_id`, `received_at`, `source` (`eotinish|manual|other`), `external_id`, `is_collective`, `signatories_count`, `summary`, `status` (`new|in_review|closed`), `confirmed_payments` (bool — заявитель подтвердил платёж застройщику), `is_verified` (bool — обращение проверено аналитиком; нужно для R4), `verified_by`, `verified_at`.
- **linked_entity**: `object_id` | `developer_id`, `kind` (`ad_account|sales_office|phone|website|bank_details`), `value`, `note`.
- **source_account**: `platform` (`instagram|tiktok|telegram|website|aggregator|outdoor|other`), `handle`, `url`, `object_id`, `developer_id`, `territory_id`, `is_watched`, `last_collected_at`.
- **ad_post**: `territory_id`, `source_account_id`, `platform`, `url`, `external_id` (уник. с platform), `author`, `published_at`, `captured_at`, `text`, `phones` (text[], E.164), `links` (text[]), `object_id`, `link_confidence` (0..1), `link_method` (`account|phone|name|manual`), `payment_schemes` (text[] из `booking|down_payment|deposit|installment|nonstandard_contract`; подтверждённые), `claimed_readiness_pct`, `price_before_completion` (bool), `llm_extraction` (jsonb), `llm_status` (`none|pending|done|failed|disabled`), `status` (`captured|verification|removed_saved`), `max_phrase_weight`, `total_phrase_weight`, `is_outdoor`, `location` (Point, для наружной), `last_checked_at`, `removed_detected_at`, `capture_status` (`pending|done|failed`), `capture_error`, `is_demo`.
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
- **app_setting**: `key` (PK), `value` (jsonb). Ключи и умолчания: `review_days=5`, `ad_window_days=30`, `readiness_gap_pp=20`, `significant_delay_days=90`, `zone_yellow_min=25`, `zone_red_min=60`, `complaints_threshold=3`, `stalled_days=30`, `recheck_after_days=3`, `link_confidence_threshold=0.8`, `green_interval_days=30`, `yellow_interval_days=7`.

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
- **Связывание с объектом**, по приоритету: аккаунт привязан к объекту (кроме сохранённого поиска агрегатора) → совпал телефон из `linked_entity`/`developer.phones` → нечёткое совпадение названия или алиаса (rapidfuzz `token_set_ratio`/100). Если `link_confidence < link_confidence_threshold` или кандидатов несколько, статус `verification`.
- **LLM**: Ollama `/api/chat` со structured output (`format` — JSON-схема `{findings: [{category, quote, confidence: 0..1}], payment_schemes: [...], claimed_readiness_pct: int|null, price_before_completion: bool, confidence: 0..1}`; находки с `confidence < 0.5` помечаются «неуверенно»); результат пишется в `llm_extraction` и как `phrase_hit` с `detected_by=llm, confirmed=null`. В `payment_schemes`/`claimed_readiness_pct` поста он попадает только после подтверждения пользователем.
- **Перепроверка**: через `recheck_after_days` воркер проверяет URL (HTTP-статус и признаки удаления). Если публикация удалена, статус `removed_saved`; доказательства не трогаются.
- **Наружная реклама**: ручной ввод (текст, фото, геоточка, `is_outdoor=true`).
- **Коллекторы (фаза 2, раздел 10.1)**: `collectors/base.py`: `class Collector(Protocol): platform; capture_urls: bool; def handles(account) -> bool; def collect(account, since, is_known) -> Iterable[CollectedPost]`. `CollectedPost` несёт `media_urls`. Реестр коллекторов по `platform`; регистрируются только включённые (`collectors.register_enabled`). Сборщик возвращает и уже известные посты окна, чтобы заметить правку текста.

## 6. Оценка риска (модель кейса Codemasters 8.0)

Риск — оценка необходимости проверки, а не юридическое заключение. Расчёт детерминирован: одинаковые подтверждённые данные дают одинаковый результат.

### 6.0. Правовое основание объекта (`legal_basis_status`, вычисляется)

Применимые основания (Закон РК «О долевом участии в жилищном строительстве»): гарантия Единого оператора (АО «КЖК») — `document.doc_type=guarantee`; разрешение МИО (в т.ч. при участии БВУ или после возведения каркаса) — `doc_type=dsu_permit`.

- `confirmed` — есть документ `guarantee` или `dsu_permit` со статусом `confirmed`.
- `absent_established` — подтверждённых нет, на проверке (`checking`) нет, и **оба** типа (`guarantee` и `dsu_permit`) проверены со статусом `not_found`. Только это состояние даёт R1.
- `unknown` — всё остальное (нет записей о проверке, проверка идёт, проверен только один тип). Даёт флаг «Нужна проверка» `legal_basis_unknown`, 0 баллов.

Отсутствие только разрешения МИО при подтверждённой гарантии — не R1 (сценарий C).

### 6.1. Факторы (стартовые веса — из кейса)

| code | Метка | Условие срабатывания | Вес |
|---|---|---|---|
| `r1_no_legal_basis` | R1 | `legal_basis_status = absent_established` | +35 |
| `r2_money_offer` | R2 | за `ad_window_days` у связанной публикации с подтверждённой привязкой (статус не `verification`) есть словарная формулировка (не отклонённая аналитиком) или подтверждённая LLM-формулировка категорий `booking|down_payment|deposit|installment|preliminary_contract|covert_contract`, либо подтверждённая схема `payment_schemes` | +25 |
| `r3_active_ads` | R3 | за `ad_window_days` есть хотя бы одна связанная публикация с подтверждённой привязкой (статус не `verification`), объект не `completed` | +10 |
| `r4_collective_complaint` | R4 | есть обращение `is_collective=true` и `is_verified=true` со статусом ≠ `closed` | +15 |
| `r5_readiness_mismatch` | R5 | `readiness_claimed_pct − readiness_actual_pct ≥ readiness_gap_pp` (по умолчанию 20), оба значения имеют источник и дату (связанная публикация с подтверждённой привязкой — статус не `verification` — и фотофиксация) | +10 |
| `r6_stalled_or_delayed` | R6 | `construction_status=stalled` и `stalled_since` не позже чем `stalled_days` назад, или просрочка: `forecast_completion − planned_completion ≥ significant_delay_days` (по умолчанию 90) либо `planned_completion` прошла более `significant_delay_days` назад и объект не `completed` | +5 |

Балл = min(100, сумма весов активных сработавших факторов). Отрицательных факторов нет.

Флаги «Нужна проверка» (`needs_check`, 0 баллов, показываются отдельно): `legal_basis_unknown`, `complaint_unverified` (коллективное обращение без `is_verified`), `readiness_unverified` (заявленная готовность есть, фотофиксации нет), `ai_hypotheses_pending` (есть неподтверждённые LLM-находки по связанным публикациям), `link_unverified` (связанные публикации в статусе `verification`).

### 6.2. Зоны

| Зона | Правило | Действие |
|---|---|---|
| green | балл 0–24 | плановый мониторинг (раз в `green_interval_days`), история сохраняется |
| yellow | балл 25–59, **а также 60+ без одновременных R1 и R2** | углублённая ручная проверка (раз в `yellow_interval_days`) |
| red | балл ≥ 60 **и** сработали R1 и R2 | приоритетная сигнальная карточка (черновик), ожидает подтверждения человеком |

Пороги — настройки `zone_yellow_min=25`, `zone_red_min=60`. `zone_reasons` — коды, определившие зону (например `score_25_59`, `r1_and_r2`, `score_60_without_r1_r2`).

### 6.3. Расшифровка (`risk_score.breakdown`)

```json
{"factors": [{"code": "r2_money_offer", "label": "R2", "weight": 25, "triggered": true,
              "evidence": [{"type": "ad_post", "id": 55, "phrase_hit_id": 301, "fragment": "внесите депозит"}],
              "detail": {"...": "..."}}],
 "needs_check": [{"code": "legal_basis_unknown", "detail": {}}],
 "legal_basis_status": "unknown"}
```

В `factors` — все активные факторы, в том числе несработавшие (`triggered=false`). Для R2 в evidence — фрагмент-основание (текст фразы) и ссылка на публикацию/hit. *(Если в коде уже используется список вместо объекта — допустимо оставить список факторов в `breakdown`, а `needs_check` и `legal_basis_status` отдать отдельными полями `risk_score`; frontend выравнивается по факту.)*

### 6.4. `key_status` объекта (для дашборда)

Первый сработавший по приоритету: `no_legal_basis_with_offer` (R1+R2), `no_legal_basis` (R1), `money_offer` (R2), `legal_basis_unknown`, `stalled` (detail `stalled_days` → «простой N дней»), `delayed`, `collective_complaint`, `readiness_mismatch`, `active_ads`, `ok`.

### 6.6. Контрольные тест-сценарии кейса (обязательны в автотестах и демо-данных)

| Кейс | Данные | Ожидание |
|---|---|---|
| A | основание не проверено (`unknown`), есть платная бронь | R2 25 + R3 10 = 35 → **yellow**; отсутствие данных не превращается в R1, флаг `legal_basis_unknown` |
| B | установлено отсутствие основания (`absent_established`) + депозит | R1 35 + R2 25 + R3 10 = 70 → **red**; авто-черновик карточки ожидает подтверждения человеком |
| C | действующая гарантия подтверждена, обычная реклама без предложения денег | R3 10 = 10 → **green**; отсутствие отдельного разрешения МИО не даёт R1 |

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

`DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_EVIDENCE`, `EVIDENCE_LOCK_MODE`, `EVIDENCE_RETENTION_DAYS`, `TSA_URL`, `JWT_SECRET`, `JWT_TTL_MINUTES`, `LLM_ENABLED`, `OLLAMA_URL`, `OLLAMA_MODEL=qwen3.5:9b-q6k`, `LLM_TIMEOUT_S`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `CORS_ORIGINS`, `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`, `HOMEPORTAL_SYNC_ENABLED`; фаза 2: `COLLECT_TELEGRAM_ENABLED`, `COLLECT_OLX_ENABLED`, `COLLECT_KRISHA_ENABLED`, `INSTAGRAM_GRAPH_TOKEN`, `INSTAGRAM_GRAPH_USER_ID`, `INSTAGRAM_GRAPH_API_VERSION`, `COLLECT_REQUEST_DELAY_S`, `COLLECT_MAX_PAGES`, `COLLECT_USER_AGENT`, `OCR_ENABLED`, `OCR_LANGUAGES`, `TELEGRAM_BOT_TOKEN`, `BOT_REPORTS_PER_HOUR`. Секреты — только в `.env` (в git не попадает), в репозитории только `.env.example`.

## 10. Фаза 2: сбор, OCR, бот, связи, история

Решения пользователя от 13.10.2026. Схема — миграция `0005`.

### 10.0 Общие правила

- `ad_post.origin`: `manual` (внесено сотрудником), `capture` (сотрудник добавил по ссылке), `collector` (сборщик), `citizen` (Telegram-бот).
- Публикация, которую не смотрел сотрудник (`collector`, `citizen`), не влияет на балл, пока человек не подтвердит привязку. Исключение — аккаунт, который сотрудник сам привязал к объекту (OPEN_QUESTIONS 29).
- Сборщики и бот выключены по умолчанию. Материалы сдачи (README, скриншоты, видео) — только на вымышленных ЖК (OPEN_QUESTIONS 30).

### 10.1 Сборщики

- `telegram`: публичный канал, `https://t.me/s/<handle>`, пагинация `?before=<id>`. Ответ 302 на адрес без `/s/` — у канала нет веб-превью (ошибка источника).
- `aggregator`: сохранённый поиск. В `source_account.url` — URL поиска на `olx.kz` (читается JSON `/api/v1/offers/` с теми же фильтрами) или `krisha.kz` (страница списка и детальные страницы, `window.data`). Другие хосты не принимаются. `handle` — название поиска. Поиск находит объявления любых продавцов, поэтому к объекту он не привязывается (422 `aggregator_object_not_allowed`). Страница объявления браузером не снимается: на ней имя и контакты продавца, копией служат разобранный текст и фото. Объявление OLX опознаётся по коду `-ID…` в адресе, и правка заголовка не создаёт дубль.
- `instagram`: только официальный Graph API, Business Discovery (`INSTAGRAM_GRAPH_TOKEN`, `INSTAGRAM_GRAPH_USER_ID`). Работает только для бизнес-аккаунтов и аккаунтов авторов.
- TikTok автоматически не собирается (OPEN_QUESTIONS 31): только по ссылке.
- Каждый сборщик включается своим флагом (у Instagram — токеном и `INSTAGRAM_GRAPH_USER_ID`). Выключенный сборщик не регистрируется, и его источники пропускаются. Токен Instagram передаётся в заголовке `Authorization`, не в адресе (адреса пишутся в журналы).
- OLX и Krisha закрыты WAF для небраузерных клиентов (OPEN_QUESTIONS 36). Krisha не опирается на `since`: открываются только ещё не сохранённые объявления, не больше 20 за запуск (OPEN_QUESTIONS 37).
- `CollectedPost.text`: то, что видит читатель, без адресов в скобках после ссылок (как в снимке страницы и в виджете перепроверки, иначе каждый пост со ссылкой получал бы ложную версию). Адреса за словами ссылок лежат в `CollectedPost.links`, сохраняются в `ad_post.links` и переживают повторный анализ. Из текста чужих источников убираются символы NUL и последовательность маркера OCR.
- `CollectedPost.media_urls`: фото поста. Они скачиваются (не больше 10 МБ, jpeg/png/webp по сигнатуре) и сохраняются как evidence `photo`, затем идут на OCR.
- Пост уже известен (`platform`, `external_id`), а текст изменился → строка `ad_post_version` с `source=collector`.
- Ошибка источника записывается в `last_error` и `last_error_at`; успешный сбор очищает их. При переходе источника из «ок» в «ошибка» администраторам приходит уведомление `collector_failed`.
- Вежливость: пауза `COLLECT_REQUEST_DELAY_S` между запросами, не больше `COLLECT_MAX_PAGES` страниц за запуск, сбор только до `since`. Персональные данные продавцов (имена и телефоны в профиле OLX) не сохраняются.
- Запуск сбора: каждый источник собирает не больше одного запуска за раз (ключ `collect:lock:<id>` в Redis, TTL 30 минут, снимается по окончании); занятый источник пропускается, кнопка отвечает 409 `collect_in_progress`. Сеть не используется внутри транзакции БД: посты читаются, затем каждый сохраняется и фиксируется отдельно, после этого скачиваются его фото, и сразу ставится в очередь конвейер. Сбой одного источника не прерывает запуск. Если конвейер поставить в очередь не удалось, статусы фиксации и OCR становятся `failed`.
- Расписание: `collect.run_all` каждые 3 часа. `collect.source(source_id)` — кнопка «Собрать сейчас» (admin, mio_officer); `POST /source-accounts/{id}/collect`.
- Интерфейс: раздел администрирования «Источники». В нём список источников, добавление, включение и выключение наблюдения, состояние сборщиков по платформам (`GET /source-accounts/collectors`), последний сбор и ошибка, «Собрать сейчас».

### 10.2 OCR

- Задача `nlp.ocr` (очередь `nlp`) стоит в цепочке после фиксации и до анализа: `capture → ocr → analyze → link → llm`.
- Вход — evidence `photo` публикации (скриншоты страниц не распознаются). Tesseract, языки `OCR_LANGUAGES`.
- Распознанный текст дописывается в конец `ad_post.text` после маркера `\n\n[OCR]\n`. Текст из внешних источников (сборщик, ручной ввод, сообщение гражданина) очищается от такой последовательности, чтобы он не выдавал себя за распознанный. Повторный запуск заменяет только часть после маркера, поэтому смещения фраз в исходном тексте не меняются (OPEN_QUESTIONS 35).
- `ocr_status`: `pending`, `done`, `failed`; NULL — фото нет. При `OCR_ENABLED=false` шаг ничего не делает.
- Интерфейс: часть после маркера показывается отдельным блоком «Текст с изображения (распознан автоматически)», подсветка фраз в нём работает.

### 10.3 Граф связей и кандидаты в источники

- `GET /graph?object_id=|developer_id=|territory_id=` → `{nodes, edges, findings}` в зоне доступа.
  - Узлы: `developer`, `object`, `phone`, `account`, `ad`.
  - Рёбра: застройщик–объект; объект или застройщик–телефон (`linked_entity`, `developer.phones`); объект или застройщик–аккаунт (`source_account`, `linked_entity ad_account`); публикация–объект; публикация–телефон; публикация–аккаунт.
- Находки (`findings`): телефон или аккаунт, который связывает объекты разных застройщиков.
- Кандидаты в источники: аккаунты из ссылок в публикациях (`instagram.com/<x>`, `t.me/<x>`, `tiktok.com/@<x>`), которых нет среди источников и которые не отклонены.
  - `GET /source-suggestions`.
  - Принять → `POST /source-accounts`.
  - Отклонить → `POST /source-suggestions/dismiss` (`dismissed_source_suggestion`).
- Демо-сюжет: три вымышленных застройщика с общим телефоном и общими аккаунтами.

### 10.4 Telegram-бот для граждан

- Отдельный сервис `bot` (профиль compose `bot`) на python-telegram-bot, long polling. Пишет в БД через модули приложения.
- «Сообщить о рекламе»: текст, ссылка, фото или пересланный пост.
  - Создаётся `ad_post` с `origin=citizen`. Город выбирает гражданин, фото сохраняются как evidence.
  - Публикация идёт по обычному конвейеру.
  - Сотрудникам МИО этой территории приходит уведомление `citizen_report`.
- «Жалоба»: гражданин выбирает ЖК из найденных по названию. Создаётся `complaint` с `source=telegram`, не проверенная, поэтому на R4 она не влияет до проверки.
- «Проверь ЖК»: бот отвечает только фактами реестра на дату (правовое основание, застройщик, стадия) и даёт общий совет. Балл и зону не сообщает (OPEN_QUESTIONS 33).
- Персональные данные: имя, username и телефон гражданина не сохраняются. Частота ограничивается по HMAC идентификатора в Redis.

### 10.5 Машина времени

- История баллов восстанавливается тем же движком по датам фактов: `trigger=replay`, `calculated_at` равно дате среза.
  - Публикации берутся по `published_at`, жалобы по `received_at`, проверки документов по дате проверки.
  - Стадия и готовность берутся текущие, потому что их истории нет (OPEN_QUESTIONS 34).
- `GET /dashboard/timeline?from=&to=&step=week` → срезы зон по объектам. На карте ползунок времени и воспроизведение.
- В демо — история вымышленных ЖК за 6 месяцев.

### 10.6 «Удалили — а у нас осталось»

- `ad_post.text` — сохранённый оригинал. `ad_post_version` — более поздние тексты, которые от него отличаются: только добавление, с sha256 и ссылкой на снимок.
- Источники версий: повторная фиксация (`capture`), сборщик (`collector`), перепроверка (`recheck`).
  - Повторная фиксация пишет версию только для постов соцсетей (telegram, instagram, tiktok) и не для сообщений граждан: у сайтов и агрегаторов снятый текст — вся страница.
  - Перепроверка читает текст только у поста Telegram (`t.me/<канал>/<id>`, виджет `?embed=1`). Там же она видит удаление: виджет показывает «Post not found», тогда как сама страница поста отвечает 200.
- Интерфейс: сравнение оригинала и последней версии (удалённые слова зачёркнуты), время фиксации, sha256 и метка времени снимка, «удалено через N ч после фиксации».

### 10.7 Живая лента («островок»)

- `GET /activity?after=<cursor>` → события в зоне доступа:
  - получена публикация (с `origin`);
  - изменился балл;
  - изменилась зона;
  - карточка создана или направлена.
- Пилюля вверху экрана. Пока вкладка видима, она опрашивает ленту раз в 4 с, раскрывается при новом событии, а по щелчку ведёт к объекту или публикации.

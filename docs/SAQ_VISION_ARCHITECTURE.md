# SAQ VISION — архитектура (Этап 0)

План и целевое поведение — [SAQ_VISION_PLAN.md](SAQ_VISION_PLAN.md). Здесь — как модуль встраивается в текущий
код, принятые решения и контракт API. Журнал выполнения — [SAQ_VISION_PROGRESS.md](SAQ_VISION_PROGRESS.md).

## 1. Что есть в коде и что из этого следует

| Факт (аудит 16.10.2026) | Решение |
|---|---|
| `POST /objects/{id}/inspections` требует `readiness_pct` и переписывает `readiness_actual_pct`, затем пересчитывает риск | Не используем. Своя сущность `vision_session`, на готовность и R1–R6 не влияет |
| `Evidence` допускает ровно одного владельца из 4 (CHECK `exactly_one_owner`, `EvidenceLink`, `can_access_evidence`) | Кадры и оригиналы Vision **не** являются `Evidence`: свои таблицы и свой бакет. `Evidence` создаётся только при публикации рекламы (владелец — `ad_post`), инварианты не трогаем |
| `read_upload()`/`put_evidence()` держат файл целиком в памяти, лимит 25 МБ, сигнатуры только JPEG/PNG/WebP/PDF | Своя потоковая загрузка: файл из multipart читается кусками (Starlette сбрасывает его на диск), sha256 и размер считаются на сервере, в MinIO — `put_object` с `length=-1` (S3 multipart внутри minio-py). Сигнатуры видео проверяются по magic bytes, кодеки и длительность — `ffprobe` в воркере |
| Нет presigned URL; файлы отдаются через API-прокси с проверкой доступа | Так же: `GET /vision/.../content` со своей проверкой территории |
| OCR: только `recognise_ad()`; примитивы `_prepare`, `clean_text`, Tesseract `rus+kaz+eng`; Tesseract есть только в образе `worker` | Публичная функция `ocr_image(bytes) -> OcrResult` в `nlp/ocr.py`; OCR выделенной области — Celery-задача в очереди `vision` |
| `/ads/manual`: логика внутри роутера | Вынести создание ручной публикации в `ads/service.create_manual_ad(...)` без изменения поведения роутера; Vision вызывает её напрямую (не HTTP) |
| ffmpeg нигде не установлен | Новая стадия Dockerfile `vision` (= `worker` + ffmpeg), сервис `vision-worker` в compose-профиле `vision` |
| Celery автодискаверит `tasks.py` всех модулей | `vision/tasks.py` подхватится сам; очередь `vision` добавляется в `QUEUES`, основной `worker` её **не** слушает |
| Роли: операционные действия — `StaffUser` (admin + mio_officer); gask/law — только сигнальные карточки | Vision — только `StaffUser`. Чужая территория → 404 |
| У фронта нет флагов; карточка ЖК — одна страница из панелей | `GET /vision/config` (404, если модуль выключен) управляет видимостью вкладки; в карточке — новая панель после «Фотофиксаций» |
| nginx: `client_max_body_size 50m`, `proxy_request_buffering off` | Отдельный `location /api/v1/vision/` с лимитом под `VISION_MAX_VIDEO_MB` и увеличенным таймаутом |

## 2. Подключаемость

- `VISION_ENABLED=false` по умолчанию. Выключен — роутер не регистрируется (все `/api/v1/vision/*` → 404), задачи
  не ставятся, бакет не создаётся. Таблицы создаются миграцией всегда (Alembic один на всё приложение), пустые таблицы
  на работу SAQ не влияют.
- Настройки (`app/config.py`): `vision_enabled`, `s3_bucket_vision="vision"`, `vision_max_photo_mb=25`,
  `vision_max_video_mb=1024`, `vision_max_duration_seconds=1800`, `vision_frame_interval_seconds=3`,
  `vision_max_frames=400`, `vision_detector_backend="disabled"`. Concurrency — параметр команды `vision-worker`.
- Режим детектора: `disabled` (по умолчанию; находки создаёт человек, OCR — настоящий Tesseract) или
  `experimental_pretrained` (Этап 4: Grounding DINO tiny без дообучения, `VISION_DETECTOR_BACKEND=grounding_dino`).
  API (`/vision/config`) и UI всегда показывают режим; результаты модели — подсказки для человека, не вердикт.

## 3. Данные (миграция `0006`)

Все таблицы `IdMixin` + timestamptz, enum — VARCHAR + CHECK (`enum_type`), как в остальной схеме.

- **vision_session** — `territory_id` (NOT NULL, из ЖК или территории пользователя), `object_id` (nullable),
  `source` (`drone|camera|phone|other`), `captured_at`, `note`, `status` (`open|reviewed`), `reviewed_by/at`,
  `created_by`, `is_demo`. Привязку к ЖК меняет только человек (`PATCH`).
- **vision_asset** — `session_id`, `kind` (`photo|video`), `original_name`, `content_type`, `size_bytes`, `sha256`,
  `bucket`, `s3_key`, `width`, `height`, `duration_ms`, `lat/lon` (`location`), `taken_at` (EXIF), `status`
  (`queued|processing|ready|failed`), `error_code`, `uploaded_by`. Уникальность `(session_id, sha256)` —
  повторная загрузка того же файла возвращает существующий asset без новой задачи.
- **vision_job** — `asset_id`, `kind` (`extract_frames|ocr_region`), `status` (`queued|running|completed|failed`),
  `progress` 0–100, `attempts`, `error_code`, `error_message`, `started_at/finished_at`, `idempotency_key` (unique).
- **vision_frame** — `asset_id`, `timestamp_ms` (NULL для фото), `bucket/s3_key` оригинального кадра,
  `preview_key`, `width/height`, `sharpness`, `usable`. Для фото кадр создаётся синхронно при загрузке
  (без воркера: фото должны работать и без него); для видео — воркером.
- **vision_finding** — `session_id`, `frame_id` (nullable), `bbox` (JSONB `{x,y,w,h}` в долях исходного кадра),
  `category` (`outdoor_ad|fence|site_gate|waste_container|wheel_wash|other`), `status`
  (`observed|possible_noncompliance|insufficient_evidence|not_applicable`), `origin` (`manual|model`),
  `confidence`, `model_version`, `note`, `review_state` (`pending|confirmed|rejected|needs_more_evidence`),
  OCR: `ocr_status` (`pending|done|failed`), `ocr_text` (как распознано), `ocr_confidence`, `ocr_engine`,
  `confirmed_text` (то, что подтвердил человек), `ad_post_id` (unique, после публикации), `created_by`.
- **vision_review** — append-only (триггер `forbid_modification()` как у `ad_post_version`): `finding_id`,
  `action` (`confirm|reject|needs_more_evidence|not_applicable|comment`), `comment`, `reviewer_id`, `created_at`.
  Текущее `review_state` находки обновляется, история — здесь и в `audit_log`.
- `AdOrigin` получает значение `vision`; CHECK `ad_post` расширяется в той же миграции.

### Этап 4 (миграция `0008`)

- **vision_run** — один проход детектора: `session_id`, `asset_id` (nullable: NULL — вся сессия), `status`
  (`queued|running|completed|failed`), `model_version` (`grounding-dino-tiny@<12 символов коммита>`), `config` JSONB
  (пороги, промпты, `max_side`, `device`, `batch_size`), `frames_total/frames_done`, `error_code`,
  `started_at/finished_at`, `created_by` (NULL — запущен автоматически), `created_at`.
- **vision_detection** — сырые рамки: `run_id`, `frame_id`, `category`, `label` (сработавшая фраза), `bbox`
  (доли кадра), `confidence`, `group_key` (одна физическая сущность на соседних кадрах одного ассета).
- `vision_finding.run_id`, `vision_finding.detection_id` (nullable FK: репрезентативная рамка группы).
- Категория `debris` (мусор/навалы) добавлена в CHECK `vision_finding.category`.
- Группировка: детекции одной категории на **последовательных пригодных кадрах одного ассета** с IoU ≥ 0.3 (в долях
  кадра) образуют группу (жадное сопоставление по убыванию IoU, один к одному); на группу — одна находка модели,
  репрезентативная рамка — с максимальной уверенностью. Фото — каждая рамка своя группа. Счётчики не раздуваются.
- Правила статуса (план §5): `fence|site_gate|waste_container|wheel_wash|outdoor_ad` → `observed`; `debris` →
  `possible_noncompliance` (проверяет человек); **отсутствие категории никогда не порождает находку** — итог прогона
  `summary` показывает по каждой категории число найденных групп, 0 читается как «не обнаружено — данных недостаточно
  для вывода». Все находки модели: `origin=model`, `review_state=pending`, `confidence`, `model_version`, `run_id`.
  Решения людей новым прогоном не затрагиваются: прогон только добавляет свои находки (повторы объектов между
  прогонами возможны — это отдельные находки на проверку).

## 4. API (`/api/v1/vision`, только `StaffUser`, территориальный scope, ошибки `api_error`)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/vision/config` | `{enabled, detector_mode: disabled\|experimental_pretrained, detector_model, ocr_enabled, max_photo_mb, max_video_mb, max_duration_seconds}` |
| POST | `/vision/sessions` | JSON `{object_id?, territory_id?, source, captured_at?, note?}` → `SessionDetail` |
| GET | `/vision/sessions` | фильтры `object_id, source, status`, `limit/offset` → `Page[SessionListItem]` |
| GET | `/vision/sessions/{id}` | `SessionDetail` (assets с прогрессом, находки, `runs[]` с `summary` по категориям) |
| PATCH | `/vision/sessions/{id}` | `{object_id?, note?, source?, captured_at?}` — ручная привязка к ЖК |
| POST | `/vision/sessions/{id}/reviewed` | отметить сессию проверенной (не автоматически) |
| POST | `/vision/sessions/{id}/reanalyze` | новый прогон детектора по всем пригодным кадрам → `SessionDetail`; 409 `detector_disabled`, 409 `run_in_progress` |
| POST | `/vision/sessions/{id}/assets` | multipart `file` (одно фото или видео) → `AssetOut`, 201 / 200 при дубле |
| POST | `/vision/assets/{id}/retry` | повторить упавшую обработку видео |
| GET | `/vision/assets/{id}/content` | оригинал (стрим) |
| GET | `/vision/sessions/{id}/frames` | `limit/offset` → `Page[FrameOut]` |
| GET | `/vision/frames/{id}/content?variant=preview\|original` | изображение кадра |
| POST | `/vision/sessions/{id}/findings` | ручная находка `{frame_id?, bbox?, category, status, note?}` |
| GET | `/vision/findings/{id}` | находка + история решений |
| POST | `/vision/findings/{id}/review` | `{action, comment?, status?}` |
| POST | `/vision/findings/{id}/ocr` | запустить OCR области (только `outdoor_ad` с кадром и bbox) |
| POST | `/vision/findings/{id}/publish-ad` | `{text, object_id?}` после подтверждения → `{ad_id}`; повтор → тот же `ad_id` |

Для объявления в `AdDetail` добавляется `vision_source: {session_id, finding_id, frame_id, timestamp_ms} | null`.

## 5. Обработка

- Celery-очередь `vision`; задачи `vision.extract_frames(job_id)`, `vision.ocr_region(finding_id)`;
  `acks_late`, ограниченные повторы, идемпотентность по `job.status`/`idempotency_key`: повторная доставка
  завершённой задачи — no-op; кадры перезаписываются только для незавершённой задачи (старые кадры этой задачи
  удаляются перед повтором).
- Видео: оригинал скачивается во временный каталог потоково → `ffprobe` (контейнер, видеодорожка, длительность,
  размер; иначе `failed` с кодом) → `ffmpeg -vf fps=1/N` в JPEG → фильтр резкости (дисперсия градиента PIL) →
  dedup по dHash → кадр (оригинал) + превью (≤640 px) в бакет `vision`. Временный каталог удаляется всегда.
  Внешние процессы — `subprocess.run([...])` со списком аргументов и таймаутом, без shell.
- OCR: кроп `bbox` из **оригинального** кадра → `ocr_image()` → `ocr_text` + средняя уверенность Tesseract.
  Текст не исправляется ИИ; человек правит `confirmed_text`.
- Публикация: только при `review_state=confirmed`, категория `outdoor_ad`, непустой `text`. Создаётся `AdPost`
  (`platform=outdoor`, `is_outdoor=true`, `origin=vision`, `ocr_status=done`), фото — кадр и кроп как
  `Evidence(photo, ad_post_id)`, затем обычный `dispatch_pipeline` (анализ фраз, автопривязка — как у ручной
  рекламы, балл только после подтверждения связи человеком, как сейчас). `ad_post_id` записывается в находку
  под `SELECT … FOR UPDATE` — повтор возвращает ту же публикацию.

- Детектор (Этап 4): задача `vision.detect(run_id)` (очередь `vision`, `acks_late`, лимиты 3300/3360 с). Модель
  загружается один раз на процесс воркера (ленивый кэш); `torch`/`transformers` импортируются только в образах
  `vision`/`vision-gpu`, API их не импортирует. Только `usable` кадры; оригинал читается из MinIO, уменьшается до
  `VISION_DETECTOR_MAX_SIDE` (по умолчанию 800 px по длинной стороне) — рамки в долях, поэтому не зависят от масштаба.
  Кадры одного размера идут пачкой (`VISION_DETECTOR_BATCH_SIZE`; 0 → 2 на CPU, 8 на GPU), по ходу пишется
  `frames_done`. Детекции и находки пишутся одной транзакцией с завершением прогона: упавшая попытка ничего не оставляет,
  повторная доставка начинает заново (своё без решений удаляется), завершённый прогон — no-op. Ошибки:
  `detector_unavailable`, `detector_error`, `frame_missing`, `storage_error|storage_unavailable`, `processing_timeout`,
  `queue_unavailable`.
- Автозапуск (если бэкенд не `disabled`): **один прогон на ассет** — после успешного `extract_frames` видео и после
  загрузки фото (фото-кадр создаётся синхронно). Пачка из N фото даёт N мелких прогонов в очереди воркера (каждый — один
  кадр; модель загружена один раз), а не один прогон на всю сессию: так прогресс и сбой изолированы по файлам. Ручной
  `reanalyze` — один прогон на всю сессию (`asset_id = NULL`); пока в сессии есть прогон в очереди или выполняется,
  повторный запрос — 409. `processing` сессии истинно и пока прогон `queued|running`.
- Устройство: `VISION_DETECTOR_DEVICE=auto|cpu|cuda` (`auto` → CUDA, если видна). Образ `vision` — CPU-колёса torch,
  `vision-gpu` — CUDA 12.8; в прогон записывается фактическое устройство (`config.device`). Запускать нужно один из
  воркеров `vision-worker` / `vision-worker-gpu`, не оба. Оценка качества и скорости — [SAQ_VISION_EVAL.md](SAQ_VISION_EVAL.md).

## 6. Что не делаем

Дообучение и метрики precision/recall (нет размеченного набора), сравнение версий моделей, импорт с носителя/камер, resumable
upload, Object Lock-ретеншн сверх настроек evidence (бакет `vision` создаётся с Object Lock и той же политикой
`EVIDENCE_LOCK_MODE`/`EVIDENCE_RETENTION_DAYS`).

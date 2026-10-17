# SAQ VISION — журнал выполнения

Ветка `drone`. План — [SAQ_VISION_PLAN.md](SAQ_VISION_PLAN.md), архитектура — [SAQ_VISION_ARCHITECTURE.md](SAQ_VISION_ARCHITECTURE.md).

## Этап 0 — аудит и проектирование (16.10.2026) — готово

- Изучены `inspections`, `ads` (`/ads/manual`), `nlp/ocr.py`, `evidence`, `storage.py`, `uploads.py`, Celery,
  `config.py`, модели и миграции `0001–0005`, тестовые фикстуры, фронтенд (маршруты, карточка ЖК, API-клиент, i18n).
- Расхождения плана с кодом и принятые решения — в архитектуре, §1. Главные: кадры Vision не являются `Evidence`
  (инвариант одного владельца), карточка ЖК без вкладок — новая панель, ffmpeg отсутствует — отдельная стадия образа.
- Миграция: одна, `0006`.

**Следующая задача:** Этап 1 — модели, миграция, API сессий/фото/находок/решений, фронтенд.

## Этап 1 — backend (16.10.2026) — готово, фронтенд не начат

- Миграция `0006`: `vision_session/asset/job/frame/finding/review`, `ad_post.origin` + `vision`, триггеры append-only на
  `vision_review`. `alembic check` на чистой БД — без расхождений; `downgrade 0005` / `upgrade head` проверены.
  FK без `ON DELETE` (restrict): история сессий не теряется.
- Настройки `VISION_*` и `S3_BUCKET_VISION` (описаны в `.env.example`). Роутер `/api/v1/vision/*` регистрируется только
  при `VISION_ENABLED=true`; иначе маршрутов нет вовсе (404).
- Бакет `vision` с Object Lock и политикой evidence создаётся лениво (`storage.ensure_vision_bucket`) перед первой записью.
- Эндпоинты: `config`, сессии (POST/GET/GET{id}/PATCH, `reviewed`), `sessions/{id}/assets` (потоковая загрузка,
  sha256/размер на сервере, магические байты, 413/415/422, дубль → 200), `assets/{id}/content`, кадры и
  `frames/{id}/content?variant=preview|original`, находки (ручные, bbox в долях) и `review` (append-only история).
- Фото: кадр и превью (≤640 px) создаются синхронно, EXIF → `taken_at`, GPS → `location`. Видео: ассет `queued`,
  `vision_job` + `send_task("vision.extract_frames")` в очередь `vision` (сама задача — Этап 2; основной worker очередь не слушает).
- Тесты: `backend/tests/test_vision_api.py`, `test_vision_reviews_are_append_only` в `test_immutability.py`.
  Команды: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app tests && uv run pytest -q`.
- Ограничения: нет `retry`, `ocr`, `publish-ad` (Этапы 2–3); продолжительность и кодеки видео проверит воркер;
  одновременная загрузка одного и того же файла даёт 409 (уникальный индекс), не дубль.
- Решения: действие `not_applicable` переводит `review_state` в `rejected` (находка выходит из очереди) и ставит
  `status=not_applicable`; `comment` состояние не меняет. EXIF-время без смещения хранится как UTC.

## Этап 2 — видеоконвейер (16.10.2026) — готово

- `vision/media.py` (ffprobe/ffmpeg через `subprocess.run([...], timeout)`, без shell; резкость, dHash, превью, кроп) и
  `vision/tasks.py`: `vision.extract_frames(job_id)` — очередь `vision`, soft/hard лимит 1800/1860 с, до 3 повторов
  только при временных ошибках хранилища (`storage_unavailable` после исчерпания). Оригинал скачивается потоково во
  временный каталог (`TemporaryDirectory`, чистится всегда) → `ffprobe` (нужна видеодорожка, длительность ≤
  `VISION_MAX_DURATION_SECONDS`, стороны 16..8192 px) → `ffmpeg -vf fps=1/N` (кадры в исходном разрешении, поворот
  применяет сам ffmpeg) → резкость (дисперсия `FIND_EDGES` на копии ≤640 px, порог 30) и dHash.
- Решения: интервал растягивается так, чтобы всё видео уместилось в `VISION_MAX_FRAMES` (30 мин при 400 кадрах → 4,5 с);
  почти дубликат предыдущего сохранённого кадра (расстояние Хэмминга ≤ 4 из 64) не сохраняется; размытый кадр
  сохраняется с `usable=false`; ширина/высота ассета берутся из первого кадра (после поворота); `timestamp_ms` =
  индекс × интервал. Строки `vision_frame` вставляются одной транзакцией в конце, поэтому прерванная попытка не оставляет
  строк, к которым можно привязать находку; повторная доставка незавершённой задачи начинается с нуля.
  Объекты в бакете с Object Lock не удаляются: каждая попытка пишет под своими ключами
  `session/<id>/frames/<job>-<attempt>-<n>.jpg`, объекты оборванной попытки остаются сиротами (без строк).
- Коды ошибок: `video_no_stream`, `video_too_long`, `video_bad_dimensions`, `video_undecodable`, `ffmpeg_missing`,
  `video_processing_timeout`, `processing_timeout`, `source_missing`, `storage_error`, `storage_unavailable`,
  `processing_error`, `queue_unavailable`.
- `POST /vision/assets/{id}/retry`: только упавшее видео, новый job (`extract:<asset>:<n>`), иначе 409 `asset_not_failed`;
  аудит `vision_asset.retry`. Недоступная очередь при загрузке теперь переводит ассет в `failed/queue_unavailable`
  (UI перестаёт опрашивать и показывает «Повторить»).
- `GET /vision/assets/{id}/content` для видео: `Accept-Ranges`, одиночный `Range` (`a-b`, `a-`, `-n`) → 206 +
  `Content-Range`; вне файла — 416; несколько диапазонов и мусор — полный ответ 200.
- Инфраструктура: стадия `vision` в `backend/Dockerfile` (`worker` + ffmpeg 5.1, Tesseract rus/kaz/eng остаётся),
  сервис `vision-worker` с профилем `vision`, `location /api/v1/vision/` в `frontend/nginx.conf` (1100m, без буферизации,
  таймауты 600 с).
- Проверка: образ собирается (`docker build --target vision -t saq-vision-test backend`; ffmpeg/ffprobe 5.1.9, tesseract:
  eng kaz osd rus); тесты в образе — команда в [DEVELOPMENT.md](DEVELOPMENT.md): `138 passed` (vision + `test_nlp_ocr`, в т. ч. 5 тестов с
  настоящим ffmpeg: декодирование, поворот, нет видеодорожки, длиннее лимита, мусор). Запущенный стек не пересобирался.
- Ограничения: жёсткий лимит времени (SIGKILL) оставляет job в `running` — обработчика «зависших» нет; dedup/порог резкости
  подобраны эмпирически и вынесены в константы `media.py`; один ffmpeg-процесс на задачу, параллелизм задаётся
  `VISION_WORKER_CONCURRENCY`.

## Этап 3 — OCR и публикация (16.10.2026) — готово

- `nlp/ocr.py: ocr_image(bytes) -> OcrResult(text, confidence, engine)`: один вызов `image_to_data`, текст собирается из
  таблицы слов (блоки/абзацы через пустую строку, `clean_text`), уверенность — среднее по словам (без -1) в долях 0..1,
  `engine = "tesseract <версия> <языки>"`. `recognise_ad` не менялся.
- `POST /vision/findings/{id}/ocr`: `outdoor_ad` + кадр + bbox (422 `finding_not_outdoor_ad` / `frame_required`),
  `OCR_ENABLED` (409 `ocr_unavailable`), ставит `ocr_status=pending` и задачу `vision.ocr_region`; очередь недоступна — статус
  возвращается, ответ 503 `queue_unavailable`. Повтор разрешён (перезаписывает машинный вывод). Аудит `vision_finding.ocr`.
  Задача кропает bbox из оригинального кадра **после `exif_transpose`** (bbox заданы в долях «прямой» картинки), с
  отступом 5 % рамки; при ошибке Tesseract/хранилища — `ocr_status=failed` (прежний текст сохраняется), текст ошибки в лог.
- `POST /vision/findings/{id}/publish-ad {text, object_id?}`: `outdoor_ad` (422), `review_state=confirmed` (409
  `finding_not_confirmed`), статус не `not_applicable` (409 `finding_not_applicable`), нужен кадр (422). Строка находки
  блокируется `FOR UPDATE`; повтор возвращает тот же `ad_id` (200). Создание — `ads.service.create_manual_ad` (общее с
  `/ads/manual`, поведение роутера не изменилось): `platform=outdoor`, `is_outdoor`, `origin=vision`,
  `external_id=vision-finding-<id>`, координаты из GPS фото, фото = оригинал кадра + кроп (`Evidence(photo, ad_post_id)`),
  связь с ЖК только если человек передал `object_id`, иначе территория сессии. `ocr_status=done`, если OCR по находке
  выполнялся, иначе пусто. Задача `nlp.ocr` для `origin=vision` ничего не делает (текст подтверждён человеком, кадры не
  читаются повторно). Далее обычный `dispatch_pipeline`; баллы не меняются синхронно, автопривязка — как у ручных публикаций.
- `AdDetail.vision_source {session_id, finding_id, frame_id, timestamp_ms} | null` (аддитивно).
- Тесты: `test_vision_pipeline.py`, `test_vision_ocr_publish.py` (в т. ч. настоящий Tesseract на кропе, кроп с Orientation=6).

## Замечания независимого ревью Этапа 1 — исправлено

- Миграция `0007`: `vision_review.status` (nullable). `ReviewCreate.status` применяется и записывается в решение;
  `not_applicable` ставится только действием `not_applicable` (иначе 422 `status_not_allowed`); `confirm` находки со статусом
  `not_applicable` без нового статуса — 409 `finding_not_applicable`; публикация такой находки запрещена.
- Ранний отказ по `Content-Length` (ASGI-middleware `vision/limits.py`, 413 до чтения тела; зависимость FastAPI для этого не
  годится — форма разбирается раньше зависимостей). Без `Content-Length` (chunked) остаётся проверка после буферизации; nginx — 1100m.
- Загрузка не держит транзакцию БД на время хеширования и записи в MinIO: проверка доступа → коммит → хеш + запись под новым
  ключом → вставка строк; гонка дубликатов решается уникальным индексом `(session_id, sha256)` (возвращается существующий
  ассет, 200). Объект при сбое после записи остаётся сиротой в бакете (логируется). Порядок: оригинал, затем превью, затем строки.
- JPEG декодируется с `draft` (уменьшенный масштаб), `MAX_PHOTO_PIXELS` = 50 млн; размеры ассета — для «прямой» картинки.
- `ftyp`: видео только с известными брендами (isom, iso2/4/5/6, mp41/42, avc1, M4V, qt, dash, 3gp4/5, 3g2a); heic/avif/mif1/M4A → 415.
- EXIF-время без смещения трактуется во временной зоне территории сессии (по умолчанию Asia/Almaty), а не как UTC.
- Новая загрузка или находка в проверенной сессии возвращают её в `open` (`reviewed_by/at` очищаются, прежние значения — в аудите
  `vision_session.reopen`).

**Следующая задача:** Этап 4 — детектор (`vision_detection`/`vision_run`), если будет решение по модели; до того — проверка
на реальном видео и подбор порогов резкости/дубликатов.

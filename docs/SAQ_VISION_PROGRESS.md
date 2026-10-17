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

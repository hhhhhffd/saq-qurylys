# End-to-end tests

Playwright tests of the whole UI against a running stack with the demo data. They are the safety net for the UI
migration: the same tests must pass before and after it, so they know nothing about how the UI is built.

## Run

The stack must be up and seeded (`docker compose up -d`): API on `localhost:8000`, built frontend on `localhost:8080`.

```bash
cd frontend
pnpm e2e                        # the whole suite (about 1 minute)
pnpm e2e tests/04-ads           # one file; extra arguments go to `playwright test`
pnpm e2e -g "island" --headed   # one test, in a visible browser
pnpm exec playwright show-report   # HTML report of the last run
pnpm exec playwright show-trace test-results/<test>/trace.zip   # trace of a failed test
```

`pnpm e2e` is `e2e/run.sh`: it reads `INITIAL_ADMIN_PASSWORD` from the repo's `.env` into `SAQ_ADMIN_PASSWORD` (it is
never printed or written anywhere) and runs `playwright test`. Without a password the three admin tests and the admin
sign-in are skipped. Running `pnpm exec playwright test` directly works the same, with `SAQ_ADMIN_PASSWORD` set by hand.

Against the dev server (it proxies `/api` to `localhost:8000`, `API_PROXY_TARGET` changes that):

```bash
pnpm dev                                    # in another terminal
E2E_BASE_URL=http://localhost:5173 pnpm e2e
```

### Isolated UI regression suite

With the source preview running, use `E2E_BASE_URL=http://127.0.0.1:5174 pnpm exec playwright test --config=e2e/ui-mock.config.ts`.
This focused suite intercepts `/api/v1` with in-memory fixtures; it does not seed or access the shared database.

Chromium comes from `~/.cache/ms-playwright`. `@playwright/test` is pinned to 1.63.0, the version that uses the
installed `chromium-1243`; after changing the version run `pnpm exec playwright install chromium`.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `E2E_BASE_URL` | `http://localhost:8080` | where the app is served; `/api` must be reachable on the same origin |
| `SAQ_ADMIN_PASSWORD` | read from `.env` by `run.sh` | password of `admin` |
| `SAQ_DEMO_PASSWORD` | `demo-saq-2026` | password of `demo_mio`, `demo_gask`, `demo_police` |
| `E2E_WORKERS` | `1` | parallel workers; leave at 1, the specs share one database and the writing ones run last |

## How it is organised

- `auth.setup.ts` signs in through the real login form once per role (`demo_mio`, `demo_gask`, `demo_police`,
  `admin`) and saves the session to `e2e/.auth/` (git-ignored); the specs reuse it.
- `tests/NN-*.spec.ts` run in file order: read-only specs first (01-08), the ones that write data last (90-93), and
  `99-logout` at the very end: logout revokes every token of `demo_mio`, including the saved session.
- `support/i18n.ts` loads the locale files of the app (`src/i18n/locales`), so the specs assert the wording of the
  `ru` locale (and `kk` in the language test) instead of copies of it. A key that does not exist fails the test.
- `support/api.ts` talks to the backend as a role: it reads demo ids, and restores or closes what a failed run left.
- Requests to other origins (map tiles) are refused, so the suite does not need the internet.
- The browser runs with `prefers-reduced-motion: reduce`.

### Selectors

Only roles and accessible names (`getByRole`, `getByLabel`, `getByPlaceholder`, `getByText`) and URLs; no CSS classes
and no component-library DOM. Where text and roles are not enough there is a `data-testid` in the component; keep
these when restyling or replacing components:

| `data-testid` | Element | Used for |
|---|---|---|
| `risk-summary` | score row of the «Риск» panel of the object card (`RiskPanel.tsx`) | the score and the zone of an object |
| `phrase-mark` | every highlighted phrase in a publication text (`HighlightedText.tsx`) | «внесите депозит» and the other marked phrases |
| `activity-live-region` | live region of the activity island (`ActivityIsland.tsx`) | what the island announces |
| `time-machine-date` | date label of the time machine bar (`TimeMachineBar.tsx`) | the chosen date |

Besides these the suite relies on accessible names that come from the UI (they must stay when the markup changes):
the labelled regions «Объекты по убыванию риска», «Правовое основание», «История публикации», «Выбранная
публикация», the zone-counter group, the language switch showing the texts `RU` and `ҚАЗ`, the role `article` with
the name «Публикация №N» for a publication, and `aria-pressed` on the zone counters, the time-machine toggle and the
findings of the graph. Activity announcements remain available through the live region when an event arrives; an
idle monitoring caption is not part of the header.

## Data the tests leave behind

The demo database is shared and the tests do not reseed it. Repeated runs are safe; this is what stays:

- **Manual publication** (`91-manual-ad`): one publication «E2E <timestamp> Старт продаж! Забронируйте квартиру,
  первоначальный взнос 10 %» for «Берёзовая роща» per run. The object goes 0 → 35 (yellow) on the first run and stays
  at 35 afterwards, so the test asserts `>= 35` (exactly 35 when it started from 0). It also adds events to the
  activity feed.
- **Manual signal card** (`92-signal-workflow`): one new card per run for «Радужный парк», taken through
  return → edit → send to ГАСК → answer from `demo_gask` → close. The card ends `closed`, so the next run can create
  another one (an object can have only one open card). If a run stops half way, the next run (and the `finally` of the
  failed one) first drive the leftover card to `closed`. The automatic cards of the red objects are never touched.
- **Dictionary phrase** (`90-ads-mutation`): «Внесите депозит» of the «Золотая осень» publication is rejected (score
  45) and confirmed again (score 70). The score returns to 70, but the phrase stays marked «Подтверждено» instead of
  «Словарь» (the API cannot take a decision back). The test restores it in a `finally`, through the API, even when an
  assertion fails.
- Side effects of the above: audit journal entries, score history rows, and unread notifications: for `demo_mio` a
  «red zone» notice each time «Золотая осень» turns red again and a «result received» notice per signal card, for
  `demo_gask` a «card sent» notice per signal card (the bell lists them all until someone reads them).

Nothing else is written: the other specs only read. They never accept or dismiss the source candidate
`prime_estate_demo`, never change settings, and never send the automatic cards.

# UI: тема Fatality на Tailwind v4 + shadcn/ui (контракт переезда)

Решение пользователя от 13.10.2026. Оно заменяет D16 (раньше была нейтральная светлая тема): единственная тёмная тема
в стиле чит-меню Fatality. Frontend полностью переезжает с Mantine на Tailwind v4 + shadcn/ui. Редизайн 16.10.2026 меняет домашний маршрут и порядок навигации, сохраняя роли, права, действия API, прямые ссылки
на страницы и `data-testid`. Проверка — e2e `frontend/e2e` (Playwright): существующие сценарии должны оставаться
зелёными после редизайна.

## 1. Принципы

- Одна тёмная тема: глубокий индиго, не чёрный. Плотные панели с тонкой рамкой и заголовками капсом, мелкие
  контролы, акцент — ярко-розовый.
- Розовый — только бренд и интерактив: активная вкладка, основная кнопка, включённый контрол, фокус, выделение.
- Цвета зон — только для зон. Красная зона (`#ff4d3d`, оттенок ~5°) всегда отличима от розового акцента
  (`#f0035b`, ~340°), а зона всегда подписана словом, не только цветом.
- Эффекты (свечение, анимации) — точечно: логин, логотип, счётчики, красная зона, «островок». Таблицы и формы
  остаются спокойными. Все эффекты уважают `prefers-reduced-motion`.

## UX-аудит и рабочий поток (16.10.2026)

### Продукт, роли и следующий шаг

Это кабинет сотрудников для проверки рекламы, объектов и карточек обращений по строительству. Рабочий маршрут:

**Реклама → объект → карточка → ответ получателя → проверка результата и закрытие карточки.**

Сотрудник MIO начинает с `/work`: сначала дорабатывает возвращённые карточки, затем готовит к отправке требующие подтверждения, рассматривает ответы и контролирует отправленные. Получатель по-прежнему работает в `/signals` и отвечает на направленную ему карточку. Администратор видит обзор и остаётся в режиме чтения. Главная навигация ведёт к задачам, рекламе, объектам и карточкам; карта, связи и доступные по роли источники находятся в меню инструментов.

Очередь использует только известные API статусы `returned`, `requires_confirmation`, `responded` и `sent`; числа относятся к отдельным запросам статусов, а карточки ведут на реальные страницы. API не сообщает, проверена ли реклама, поэтому отдельная очередь «непроверенная реклама» не создаётся. Красная зона формируется по R1 + R2 и порогу score 60, но это сигнал для проверки, не подтверждённое нарушение; неизвестные данные не означают отсутствие нарушения. Красная зона не назначает сотруднику задачу.

Отчёт explorer зафиксировал, что главная отправляла registry-роли на `/map`, шесть разделов были равнозначны, а источники зависели от `canEditRegistry`; путь «объявление → объект → карточка» не был показан как единый сценарий. При переходе объекта в красную зону система создаёт черновик автоматически, но это само по себе не означает назначение задачи сотруднику.

### Экспертная предварительная оценка

| Рамка | Оценка | Наблюдение и основание |
|---|---:|---|
| Useful | 4/5 | Реклама, объект и обращение поддержаны в продукте; пользователь всё ещё не понимал следующий шаг. |
| Usable | 2/5 | По сообщению пользователя путь стал понятен только после пробных переходов, а завершение осталось неясным. |
| Findable | 2/5 | Главная вела на карту, шесть разделов имели равный вес; источники зависели от роли. |
| Credible | 3/5 | Статусы и данные существуют, но значение красной зоны и следующий шаг требуют явного объяснения. |
| Desirable | 3/5 | Сохраняется намеренно выбранная тёмная брендовая тема; визуальная иерархия задач раньше была слабой. |
| Accessible | 2/5 | Предыдущая навигация прокручивалась и имела мелкие цели; полный WCAG-аудит не проводился. |
| Valuable | 4/5 | Система объединяет проверку объявления и последующее обращение, но ценность пути не была видна на входе. |
| Effectiveness | 2/5 | Неочевидно, как довести карточку от объявления до закрытия. |
| Efficiency | 2/5 | Чтобы понять структуру, приходилось открывать несколько равнозначных вкладок. |
| Engagement | 3/5 | Тема сохраняет бренд, однако интерфейс не показывал рабочую приоритетность. |
| Error tolerance | 3/5 | Есть состояния загрузки и повтор запроса, но ранее не было общей картины очереди. |
| Ease of learning | 2/5 | Пользователь после знакомства с сайтом всё ещё не знал, что делать после ответа получателя. |
| Words | 2/5 | «Сигналы» — внутренний термин; навигация теперь называет их «Карточками». |
| Visual representations | 3/5 | Иконки и цвет есть, но прежняя равная иерархия не подсказывала основной маршрут. |
| Physical objects / space | 2/5 | Предыдущая навигация прокручивалась; проверка всех размеров экранов ещё предстоит. |
| Time | 3/5 | Для запросов есть состояния загрузки и ошибки, но не было очереди на рабочем входе. |
| Behavior | 2/5 | После отправки существовали этапы ответа, проверки и закрытия, но интерфейс их не связывал. |

Оценки — экспертные гипотезы по коду, текущим маршрутам и одному сообщению пользователя, а не результаты юзабилити-теста или аналитики. Они не доказывают распространённость проблемы или улучшение после редизайна. Проверить путь отдельно с сотрудником MIO, получателем и администратором; затем повторно оценить сценарии с клавиатуры, на узком экране и при ошибках API.

### Решения

| Keep | Replace | Defer |
|---|---|---|
| Тёмная тема Fatality и текущие шрифты; API, auth guards, права, существующие прямые маршруты, детали фич и общие UI-примитивы. | Домашний экран для registry-ролей ведёт на `/work`; основная навигация группирует рабочие шаги, а «Сигналы» показываются пользователю как «Карточки». | Очередь непроверенной рекламы без API-признака проверки; автоназначение задач по красной зоне; любые обещания, что красная зона доказывает нарушение. |

Правила новой рабочей поверхности: показывать следующий реальный шаг и ссылки на существующие страницы; отдельные загрузку, ошибку с повтором и пустое состояние; не объявлять «всё готово» при сбое; не выделять нулевые счётчики; сохранять контекст статуса при переходе к списку; обеспечить видимый клавиатурный фокус и цели основных действий не менее 44 × 44 px. Получатели остаются на `/signals`; маршруты и deep links сохраняются; данные обзора загружаются только на странице с существующим `canSeeRegistry` guard.


## 2. Стек

| Что | Чем |
|---|---|
| Стили | Tailwind CSS 4.3 (`@tailwindcss/vite`), конфигурация в CSS (`@theme`) |
| Примитивы | shadcn/ui (CLI `shadcn@latest`, база Radix: `init -b radix`), компоненты в `src/components/ui/` |
| `cn` | `src/lib/utils.ts`: clsx + tailwind-merge, расширенный размерами `text-3xs`/`text-2xs` и тенями `shadow-1/2/glow/window` (без расширения merge принял бы их за цвет) |
| Иконки | `@tabler/icons-react` — одна библиотека иконок (`components.json`: `iconLibrary: "tabler"`, CLI сам генерирует tabler-импорты) |
| Тосты | `sonner` (обёртка вместо `notifications.show`) |
| Подтверждение | `AlertDialog` (обёртка вместо `modals.openConfirmModal`, тот же API `lib/confirm.tsx`) |
| Даты | `react-day-picker` 10 + `date-fns` 4 (локали `ru`, `kk`): компоненты `DateInput` и `DateTimeInput` поверх `calendar` + `popover` |
| Формы | `react-hook-form` + `zod` + `@hookform/resolvers` + shadcn `field` (вместо `@mantine/form`) |
| Хуки | `src/lib/hooks.ts`: `useDebouncedValue`, `useDebouncedCallback`, `useDisclosure`, `useElementSize`, `useReducedMotion` (вместо `@mantine/hooks`) |
| Анимации эффектов | `motion` (только для эффектов, которым он нужен) |
| Шрифты | Tektur (`@fontsource-variable/tektur`) — только капс и цифры: логотип, заголовки панелей, вкладки, счётчики, баллы; всё со строчными буквами, включая заголовки страниц и названия ЖК, — Play (`@fontsource/play`, 400 и 700): в Tektur строчная «д» нарисована как «g». Оба OFL-1.1, оба с казахскими буквами Ә Ғ Қ Ң Ө Ұ Ү Һ І и ₸ |

Новых CSS-модулей нет. Глобальный CSS (`src/theme/app.css`) — только токены, `@theme`, `@font-face`/импорт
шрифта, keyframes и переопределения MapLibre. CSS-модуль компонента удаляется, когда компонент переведён на классы.

## 3. Токены

Имена прежние (`src/theme/tokens.css`), значения новые. Tailwind получает их через `@theme inline`
(`bg-surface`, `text-text-2`, `border-border-strong`, `bg-zone-red-bg` …); shadcn-имена (`--background`,
`--primary`, `--card`, `--popover`, `--muted`, `--accent`, `--destructive`, `--input`, `--ring`) ссылаются на них.
Внимание: shadcn `--accent` — фон наведения (= наш `--hover`), а наш брендовый `--accent` у shadcn — `--primary`.

| Токен | Значение | Роль |
|---|---|---|
| `--bg` | `#0f0c20` | фон страницы |
| `--surface` | `#1a1535` | панель (группа настроек Fatality) |
| `--surface-raised` | `#221c42` | поповер, меню, модалка, шапка |
| `--surface-sunken` | `#110f24` | поле ввода, чекбокс, трек |
| `--surface-glass` | `rgba(26, 21, 53, .82)` | стеклянные бары с blur |
| `--hover` / `--pressed` | `rgba(235, 232, 253, .05)` / `.09` | наведение / нажатие |
| `--scrim` | `rgba(5, 3, 12, .72)` | подложка модалки |
| `--border` / `--border-strong` | `#2a2350` / `#3a3170` | рамки |
| `--text` / `--text-2` / `--text-3` | `#ebe8fd` / `#b5b3c9` / `#8d87b8` | текст, вторичный, приглушённый (≥ 4,5:1 на `--surface`) |
| `--text-disabled` | `#5f597d` | выключенное (как серые пункты Fatality) |
| `--accent` | `#f0035b` | бренд, заливки, крупный текст |
| `--accent-hover` | `#ff2d75` | наведение |
| `--accent-text` | `#ff5c93` | мелкий розовый текст (≥ 6:1) |
| `--accent-ink` | `#ffffff` | текст на розовом |
| `--accent-glow` | `rgba(240, 3, 91, .45)` | свечение |
| `--link` / `--focus` | `#ff7aa8` / `#ff5c93` | ссылка / кольцо фокуса |
| `--zone-green` / `-bg` / `-ink` | `#34d17b` / `rgba(52, 209, 123, .14)` / `#7ee8ad` | зелёная зона |
| `--zone-yellow` / `-bg` / `-ink` | `#f5b83d` / `rgba(245, 184, 61, .14)` / `#ffd27a` | жёлтая зона |
| `--zone-red` / `-bg` / `-ink` | `#ff4d3d` / `rgba(255, 77, 61, .15)` / `#ff8a7d` | красная зона, ошибки |
| `--zone-none` / `-bg` / `-ink` | `#7d7899` / `rgba(235, 232, 253, .06)` / `#b5b3c9` | нет оценки |
| `--graph-developer` | `#8b7cf6` | узлы застройщиков в графе (не розовые, чтобы не спорить с красной зоной) |
| `--radius-sm` / `--radius` / `--radius-lg` | `2px` / `4px` / `6px` | Fatality почти прямоугольный |
| `--shadow-1` | `0 0 0 1px var(--border)` | панель |
| `--shadow-2` | `0 12px 40px rgba(0, 0, 0, .45), 0 0 0 1px var(--border)` | поповер, модалка |
| `--shadow-glow` | `0 0 0 1px var(--accent-glow), 0 0 24px -6px var(--accent-glow)` | активное/выбранное |
| `--shadow-window` | `0 0 80px -24px rgba(240, 3, 91, .45), 0 0 0 1px var(--border)` | «окно» (логин, модалка) |
| `--font-sans` | `'Play', 'Tektur Variable', system-ui, sans-serif` | основной текст, таблицы, поля |
| `--font-heading` | `'Tektur Variable', system-ui, sans-serif` | логотип, заголовки страниц, заголовки панелей капсом, вкладки (`font-heading`) |
| `--font-mono` | `ui-monospace, 'SF Mono', Menlo, Consolas, monospace` | хэши, коды |

Цвета зон для canvas/WebGL (карта, граф) — те же значения в `components/zoneColor.ts` (`ZONE_HEX`); других копий нет.
`color-scheme: dark`; `<html class="dark">` постоянно; `meta theme-color` = `#0f0c20`, favicon — розовый на индиго.

## 4. Вид элементов

- **Панель** (группа Fatality): `bg-surface border border-border rounded`, заголовок — 11px, капс, жирный,
  `tracking-wider`, `text-text`; плотные строки «подпись слева — контрол справа» высотой 26–28px.
- **Чекбокс**: квадрат 12px, `bg-surface-sunken`, рамка `border-strong`; отмечен — розовая заливка. **Switch**:
  компактный (28×14), розовый во включённом состоянии.
- **Поле / Select / Combobox**: высота 28px, `bg-surface-sunken`, текст `text-2`, шеврон розовый, фокус — кольцо
  1px `--focus`. Ошибка — `--zone-red`.
- **Кнопки**: основная — розовая заливка, белый текст, при наведении ярче + `--shadow-glow`; вторичная —
  `bg-surface-sunken` с рамкой; призрачная — текст `text-2`, фон при наведении `--hover`; опасная — `--zone-red`.
- **Вкладки и навигация**: иконка + подпись капсом 12px; неактивная — `text-3`, активная — розовые иконка и текст
  (как MISC в Fatality), без подложки.
- **Слайдер**: розовая заливка дорожки (как «Slowwalk 100%»), бегунок минимальный.
- **Чипы/бейджи**: 10–11px, капс, тонированный фон; тона зон и нейтральный.
- **Таблица**: строки ~32px, заголовок 10–11px капсом `text-3`, наведение `--hover`, разделители `--border`.
- **Модалка**: `bg-surface-raised`, `--shadow-window`, подложка `--scrim` с blur 4px. **Тосты**: `surface-raised`,
  ошибка — красная полоса слева, успех — розовая.
- **Шапка**: полоса как заголовок окна Fatality (`surface-raised`, нижняя рамка), логотип «SAQ QURYLYS» жирным
  Tektur, «SAQ» белым, «QURYLYS» розовым, лёгкое свечение. Язык, уведомления и профиль остаются отдельными
  элементами без общей рамки.

## 5. Эффекты

Источник — React Bits (MIT + Commons Clause, встраивание в приложение разрешено) и Magic UI (MIT). Код
копируется в `src/components/fx/` с комментарием-атрибуцией в начале файла; лицензии — в `THIRD_PARTY_NOTICES.md`.
Код Aceternity и 21st.dev не копируется (неясная лицензия, нужен API-ключ): понравившиеся эффекты пишутся заново
по описанию поведения, без чтения и пересказа их исходников — это собственный код проекта.

| Свой эффект (по мотивам) | Поведение | Где |
|---|---|---|
| `GlowCard` (как Glowing Effect) | Рамка карточки подсвечивается коническим розовым градиентом, «тянущимся» к курсору, когда тот рядом; в покое — обычная рамка | Карточки и панели (список ЖК, карточка объекта) |
| `Spotlight` | Мягкий розовый конус света сверху, медленно проявляется при загрузке | Пока не используется |
| `MovingBorder` | Яркая точка-огонёк бежит по рамке кнопки | Основное действие: «Подтвердить и направить» |

| Где | Эффект |
|---|---|
| Логотип на логине | React Bits **GlitchText** в режиме `bursts`: ровный текст, раз в 6 с короткая (~0,5 с) вспышка глитча; фон логина — обычный фон темы, без Aurora и Spotlight (мешали читать); статичный при reduced motion |
| Счётчики зон, балл в карточке | React Bits **CountUp** |
| Карточка объекта красной зоны, строка списка | React Bits **BorderGlow** (розово-красное свечение рамки по курсору), спокойно в покое |
| Уведомление о событии | React Bits **StarBorder** по контуру временной карточки под шапкой; в ожидании карточка скрыта |

## 6. Карта и граф

- Подложка: OpenFreeMap `https://tiles.openfreemap.org/styles/dark` (один источник `features/map/mapStyle.ts`, его же
  использует `features/ads/PointMap.tsx`), после `style.load` перекраска слоёв в палитру: фон `#0f0c20`, вода
  `#14112f`, парки `#161232`, жилая застройка/здания чуть светлее фона, границы `#3a3170`, подписи `#8d87b8` с ореолом
  фона. Запасной растровый стиль затемняется paint-свойствами `raster-brightness-max`, `raster-saturation`.
- Граф: палитра из токенов (`--graph-developer` для застройщиков, розовое кольцо — только выделение).
- Маркеры карты: круг цвета зоны с числом риска внутри (белая цифра, на жёлтом тёмная; без оценки: серый «—»).
  Число видно с zoom 6.
- «Карта» — пункт основной навигации (после «Объектов», только для ролей с реестром); «Инструменты» без неё.
- Акцент: ссылки нейтрально-тёмные (`--link` = `--text`, подчёркивание), счётчик уведомлений тёмный; розовый только
  у главных кнопок, бренда и активного пункта навигации, чтобы красная зона не терялась.

## 7. Правила переноса

1. Сохранять API, модели, роли и права, URL существующих страниц и прямые ссылки. Домашний маршрут и подписи навигации можно менять, когда это проясняет следующий рабочий шаг.
2. Сохранять `data-testid`, роли, подписи (`aria-label`, `<label>`) — на них стоит e2e.
3. Общие компоненты (`src/components/*`) сохраняют свой API (пропсы), чтобы фичи переводились независимо.
4. Папка фичи переведена, когда в ней нет импортов `@mantine/*` и CSS-модулей; классы — Tailwind.
5. Пока переезд идёт, Mantine подключён слоем (`@mantine/core/styles.layer.css`, порядок
   `@layer theme, base, mantine, components, utilities;`) и тоже тёмный (резолвер на те же токены), чтобы
   непереведённые экраны выглядели связно. В конце `@mantine/*` и `postcss-preset-mantine` удаляются.
6. Проверка каждого шага: `pnpm typecheck && pnpm lint && pnpm build` и e2e-сценарии своей фичи.

## 8. Этапы

| Этап | Кто | Что |
|---|---|---|
| A. Фундамент | один исполнитель | Tailwind + shadcn init, токены и шрифт, `components/ui/*` в стиле Fatality, обёртки `toast`/`confirm`/даты/формы, `lib/hooks.ts`, слой Mantine (тёмный) |
| B. Перенос | параллельно, по папкам | оболочка и общие компоненты + логин + «островок»; карта + граф + «машина времени»; объекты; реклама + источники; сигналы + администрирование |
| C. Финал | ведущий | удалить Mantine, эффекты, атрибуции, README/SPEC, скриншоты, e2e целиком (сделано) |

## 9. Для переноса фич

Фундамент этапа A. Всё ниже проверено на `/_kit` (dev-страница, регистрируется только при `import.meta.env.DEV`: каждый
контрол в состояниях, панель настроек в стиле Fatality, формы, оверлеи, эффекты). Держите её открытой рядом с работой.

### 9.1 Классы Tailwind и токены

Токены (`tokens.css`) доступны как утилиты через `@theme inline` в `src/theme/app.css`; утилита читает токен напрямую,
копий значений нет. Палитры Tailwind по умолчанию отключены: есть только токены, `white` и `black`.

| Что | Классы |
|---|---|
| Поверхности | `bg-bg`, `bg-surface` (панель), `bg-surface-raised` (поповер, модалка, шапка), `bg-surface-sunken` (поле, чекбокс, трек), `bg-surface-glass`, `bg-hover`, `bg-pressed`, `bg-scrim` |
| Рамки | `border-border`, `border-border-strong` |
| Текст | `text-text`, `text-text-2`, `text-text-3`, `text-text-disabled` |
| Бренд (розовый) | `bg-primary` (заливка), `text-primary-foreground` (белый на розовом), `hover:bg-accent-hover`, `text-accent-text` (мелкий розовый текст), `text-link`, `ring-focus`, `shadow-glow` |
| Зоны | `bg-zone-red`, `bg-zone-red-bg`, `text-zone-red-ink` (так же `green`, `yellow`, `none`); `bg-graph-developer` |
| Тени и радиусы | `shadow-1`, `shadow-2`, `shadow-glow`, `shadow-window`; `rounded-sm` 2px, `rounded` и `rounded-md` 4px, `rounded-lg` и крупнее 6px |
| Шрифт и размеры | `font-sans` (Play), `font-heading` (Tektur), `font-mono`; `text-3xs` 10px, `text-2xs` 11px, `text-xs` 12px, `text-sm` 13px, `text-base` 16px; базовый текст страницы 14px |

Высота закреплённой шапки для responsive-отступа задаётся токеном `--header-h`: 56px на desktop и 92px при ширине до 62em. Событие открывается под шапкой и не занимает место в её строке; в ожидании индикатора и подписи нет.

Ловушка имён: в shadcn `accent` значит «фон наведения», а наш брендовый `--accent` у shadcn называется `primary`. Поэтому
`bg-accent` и `bg-primary` разные вещи: розовая заливка только `bg-primary` (и `text-primary`, `border-primary`), а `bg-accent`
в готовых компонентах это наведение. Остальные shadcn-имена ссылаются на токены: `bg-background`, `bg-card`, `bg-popover`,
`text-foreground`, `text-muted-foreground`, `bg-secondary`, `bg-muted`, `border-input`, `ring-ring`.

Рецепты, которых нет отдельным компонентом:

- **Панель (группа Fatality)**: `rounded border border-border bg-surface`; заголовок `border-b border-border px-3 py-1.5 text-2xs font-bold tracking-wider uppercase`;
  строка настройки `flex min-h-7 items-center justify-between gap-4 px-3`, подпись `text-sm text-text-2`.
- **Плашка-предупреждение** (замена `Alert`): `rounded border border-zone-red/40 bg-zone-red-bg p-3 text-sm text-zone-red-ink` (тон по зоне).
- **Скрытый текст**: `sr-only`. **Цифры в колонках**: `tabular-nums` (старые `.tnum`, `.muted`, `.faint`, `.panel` в `global.css` живут до этапа C).
- **Отступы Mantine в Tailwind**: `xs` 10px = `gap-2.5`, `sm` 12px = `gap-3`, `md` 16px = `gap-4`, `lg` 20px = `gap-5`, `xl` 32px = `gap-8`.
- **Слои**: порядок `theme, base, mantine, components, utilities`. Утилиты Tailwind бьют Mantine, но не бьют **внеслойный** CSS-модуль
  на том же элементе. Переводя компонент, удаляйте его модуль целиком, не оставляйте вперемешку.

### 9.2 `src/components/ui/*`: что чем заменять

Импорты `@/components/ui/<имя>`, `cn(...)` из `@/lib/utils`. Общие классы в `ui/styles.ts`: `controlClass` (поле 28px),
`popupClass` (всплывающая поверхность), `itemClass` (строка списка). Подробные пропсы смотрите в файлах: это тонкие обёртки Radix.

| Mantine | Новое | Заметки |
|---|---|---|
| `Button` | `Button` | `variant`: `default` (розовая), `secondary` (прежняя `variant="default"`), `outline`, `ghost` (прежняя `subtle`), `destructive` (прежняя `color="red"`), `link`. `size`: `xs` 20px, `sm` 24px, `md` 28px (по умолчанию), `icon`, `icon-sm`, `icon-xs`. `loading` показывает спиннер и блокирует кнопку. `asChild` для ссылок. `fullWidth` это `className="w-full"`; иконка слева или справа просто потомок `<IconX />` |
| `ActionIcon` | `Button size="icon" variant="ghost"` | `aria-label` обязателен |
| `Badge` | `Badge` | `variant`: `default` (розовый тон), `secondary` (нейтральный), `outline`, `destructive`, зоны `green`, `yellow`, `red`, `none` |
| `Modal` | `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`, `DialogFooter` | `open`/`onOpenChange` вместо `opened`/`onClose`; ширина `className="sm:max-w-lg"` на `DialogContent`; `DialogHeader` это полоса заголовка окна. Крестик встроен, его подпись берётся из i18n |
| `Drawer` | `Sheet`, `SheetContent side=…`, `SheetHeader`, `SheetTitle` | |
| `Tooltip label` | `Tooltip` + `TooltipTrigger asChild` + `TooltipContent` | `TooltipProvider` уже в Providers, задержка 250 мс как была |
| `Menu` | `DropdownMenu*` | `variant="destructive"` у `DropdownMenuItem` |
| `Popover` | `Popover`, `PopoverTrigger`, `PopoverContent`, `PopoverAnchor` | |
| `Select` | `form/SelectInput` (см. 9.4); низкоуровнево `Select*` или `Combobox` | |
| `SegmentedControl` | `ToggleGroup type="single"` + `ToggleGroupItem` | `onValueChange={(v) => v && set(v)}`: повторный клик по активному даёт пустое значение |
| `Tabs` | `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` | иконка и подпись капсом; активная розовая с подчёркиванием |
| `Table` | `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell` | строки 32px, заголовок 10px капсом |
| `Loader` | `Spinner` | наследует цвет текста, размер `size-*` |
| `Skeleton` | `Skeleton` | размер классами `h-* w-*` |
| `Avatar` | `Avatar`, `AvatarFallback`, `AvatarImage` | `size`: `sm`, `default`, `lg` |
| `Slider` | `Slider` | массив значений, два значения это диапазон |
| `Checkbox` | `Checkbox` + `Label` | 12px; подпись рядом: `Field orientation="horizontal"` |
| `ScrollArea` | `ScrollArea` | |
| `Group`, `Stack`, `SimpleGrid`, `Text` | `flex`, `flex flex-col`, `grid`, `text-sm text-text-2` | `c="dimmed"` это `text-text-2`, цвет подписей `text-text-3` |
| `Indicator`, `CopyButton`, `VisuallyHidden` | абсолютный `Badge`, `navigator.clipboard` и `toast.success`, `sr-only` | |

`Field`, `FieldLabel`, `FieldDescription`, `FieldError`, `FieldGroup`, `FieldSet`, `FieldLegend`, `FieldContent` это раскладка
формы; готовые поля лежат в `components/form`. `InputGroup*` это рамка поля с аддонами (иконка или кнопка внутри поля).
`Combobox` и `MultiCombobox` (`ui/combobox.tsx`, пропсы `options`, `value`, `onChange`, `placeholder`, `emptyText`, `onSearchChange`, `loading`,
`clearable`, `disabled`) написаны вручную по ARIA 1.2: **текстовое поле и есть `combobox`**, список это `listbox` из `option`
во всплывающем слое, фокус остаётся в поле. e2e находит их так: `getByRole('combobox', { name })`, `getByRole('option')`, `fill()` в поле.

### 9.3 Инфраструктура (стабильные API)

```ts
// src/lib/toast.ts: замена notifications.show
toast.success(message: string, options?: { title?: string })
toast.error(message: string, options?: { title?: string })   // title это первая строка, message под ней
toast.info(message: string, options?: { title?: string })
// api/queryClient.ts уже использует: ошибки через errorMessage(), meta.success -> toast.success(i18n toasts.*)

// src/lib/confirm.tsx: сигнатура прежняя
confirmAction({ title: string, message: ReactNode, confirmLabel: string, danger?: boolean, onConfirm: () => void })
// ConfirmProvider смонтирован один раз в Providers.tsx. Роль диалога `dialog` (на неё опирается e2e), не `alertdialog`

// src/lib/hooks.ts: те же семантики, что у @mantine/hooks
useDebouncedValue<T>(value: T, wait: number): [T, cancel: () => void]            // первое значение сразу
useDebouncedCallback(callback, delay: number): ((...args) => void) & { flush(): void; cancel(): void }
useDisclosure(initial = false): [opened: boolean, { open, close, toggle }]       // без колбэков onOpen/onClose
useElementSize<T extends HTMLElement = HTMLDivElement>(): { ref, width, height } // ref это колбэк-ref, border-box
useReducedMotion(): boolean                                                      // читается синхронно с первого рендера
```

`Providers.tsx`: рядом с ещё живым `MantineProvider` смонтированы `Toaster`, `TooltipProvider`, `ConfirmProvider`.
`@mantine/modals` и `@mantine/notifications` удалены из зависимостей: `modals.*` и `notifications.show` больше нет.

### 9.4 Формы: react-hook-form + zod + `components/form`

Поля с подписью, подсказкой и ошибкой. Общие пропсы: `id`, `label`, `description`, `error` (строка или `true`: только красная рамка),
`required` (звёздочка и `aria-required`, вместо `withAsterisk`), `className` (идёт на обёртку), остальное передаётся в нативный элемент.

| Файл | Значение | Заменяет |
|---|---|---|
| `TextInput`, `TextArea` (`minRows`, `maxRows`), `PasswordInput` | нативные input-пропсы, `ref` пробрасывается (работает с `register`) | `TextInput`, `Textarea` с `autosize`, `PasswordInput` |
| `NumberInput` | `value: number \| string` (`''` пусто), `onChange(number \| string)`, `min`, `max`, `step`, `allowDecimal`, `allowNegative`, `decimalScale`, `hideControls` | `NumberInput` |
| `TagsInput` | `value: string[]`, `onChange`, `splitChars`, `maxTags` | `TagsInput` |
| `FileInput` | `value: File \| null` и `onChange(file)`, либо `multiple` и `File[]`; `accept`, `clearable`, `leftSection`. Нативный input очищается после выбора, поэтому `value={[]}` работает как «добавить файлы», `resetRef` не нужен | `FileInput` |
| `DateInput` | `value: 'YYYY-MM-DD' \| null`, `onChange(string \| null)`, `minDate`, `maxDate`, `clearable`. Печатается `ДД.ММ.ГГГГ` или `ГГГГ-ММ-ДД`, корректная дата принимается сразу, недописанная при уходе возвращается к последнему значению; календарь в поповере, локаль `ru` или `kk` по языку i18n, неделя с понедельника | `DateInput` |
| `DateTimeInput` | `value: 'YYYY-MM-DD HH:mm:ss' \| null` (локальное время без пояса, как у `DateTimePicker`; в API: `new Date(value).toISOString()`) | `DateTimePicker` |
| `SelectInput` | `data: {value,label,disabled?}[]`, `value: string \| null`, `onChange(string \| null)`, `clearable`, `searchable`, `onSearchChange` (серверный поиск, включает `searchable`), `loading`, `nothingFound` | `Select`; без `searchable` это обычный `Select` Radix с ролью `combobox` и пунктами `option` |
| `MultiSelect` | `data`, `value: string[]`, `onChange`, `clearable`, `onSearchChange` | `MultiSelect` |
| `SwitchInput` | `checked`, `onCheckedChange(boolean)`, `label`, `description` | `Switch` |

Эталон: `features/login/LoginPage.tsx` (подписи, `aria` и `noValidate` сохранены). Образец:

```tsx
const { t } = useTranslation();
// схема собирается с t: сообщения zod становятся ошибками полей
const schema = useMemo(() => z.object({ name: z.string().trim().min(1, t('required')) }), [t]);
const { register, control, handleSubmit, formState: { errors } } = useForm({
  resolver: zodResolver(schema),
  defaultValues: { name: '', city: null as string | null },
});

<form onSubmit={handleSubmit(onValid)} noValidate>
  <TextInput label={t('name')} required error={errors.name?.message} {...register('name')} />
  <Controller
    control={control}
    name="city"
    render={({ field, fieldState }) => (
      <SelectInput label={t('city')} data={cities} value={field.value} onChange={field.onChange} error={fieldState.error?.message} />
    )}
  />
  <Button type="submit" loading={mutation.isPending}>{t('save')}</Button>
</form>
```

Нативные текстовые поля подключаются через `register`, остальные (числа, даты, выбор, теги, файлы, переключатели) через `Controller`.
Ошибка поля (`FieldError`) **не** `role="alert"`: e2e ждёт единственный `alert`, ошибку сервера на форме входа. Ошибку сервера выводите
отдельным `<p role="alert">`, как на логине. `NumberInput` отдаёт число или `''`: схема `z.union([z.number(), z.literal('')])` с `refine` на непустое.

### 9.5 Эффекты (`src/components/fx`)

Все стоят на месте или показываются статично при `prefers-reduced-motion` (e2e работает именно так). Цвета можно передавать токенами
(`var(--accent)`): `fx/cssColor.ts` разворачивает их для canvas и WebGL.

| Файл | Откуда | Пропсы (основные) |
|---|---|---|
| `Aurora` (default) | React Bits | `colorStops` (по умолчанию розовый, фиолетовый, индиго из токенов), `amplitude`, `blend`, `speed`, `height`, `opacity`, `intro`, `paused`, `mouseInteraction`. Контейнеру задайте размер и `relative`. Пауза вне экрана, один кадр при reduced motion |
| `GlitchText` (default) | React Bits | `children: string`, `speed`, `enableShadows`, `enableOnHover`, `shadowColors` (розовый и фиолетовый), `backgroundColor` (слой глитча заливается ею, по умолчанию `var(--bg)`; поверх Aurora `transparent`), `className` (размер, например `text-3xl`) |
| `CountUp` (default) | React Bits | `to`, `from`, `duration`, `delay`, `separator` (`' '` для тысяч), `direction`, `className`; при reduced motion сразу итоговое число |
| `BorderGlow` (default) | React Bits | `glowColor` (HSL-тройка `'338 98 48'`, красная зона `'5 100 62'`), `colors`, `backgroundColor` (по умолчанию `var(--surface)`), `borderRadius`, `glowRadius`, `glowIntensity`, `coneSpread`, `animated` |
| `StarBorder` (default) | React Bits | `as` (`'div'` для не-кнопки), `radius` (`999` для пилюли), `duration`, `color`, `trailColor`, `stars`, `glow`, `thickness`, `hover`, `className` (отступы перекрываются) |
| `GlowCard` | свой | `proximity` (80px) и пропсы `div`. Рамка подсвечивается розовым коническим градиентом к курсору; общий слушатель и rAF, CSS-переменные, без ре-рендеров; вне экрана пропускается; при reduced motion обычная рамка |
| `Spotlight` | свой | `color` (`var(--accent)`) и пропсы `div`. Первый ребёнок `relative`-контейнера; проявляется один раз |
| `MovingBorder` | свой | `duration` (3.2 с), `color`; оборачивает кнопку: `<MovingBorder><Button>…</Button></MovingBorder>`. Огонёк идёт по `offset-path: rect()` с постоянной скоростью, вне экрана пауза; без поддержки `rect()` остаётся просто рамка |

Атрибуции в начале файлов и в `THIRD_PARTY_NOTICES.md` (React Bits, shadcn/ui, Tektur и Play OFL-1.1, OpenFreeMap, OpenMapTiles, OSM).
Keyframes эффектов и анимации `animate-glitch-*`, `animate-spotlight`, `animate-moving-border` лежат в `app.css`.

### 9.6 Mantine удалён (этап C)

Переезд завершён 14.10.2026: пакетов `@mantine/*`, `postcss-preset-mantine`, `theme/theme.ts` и CSS-модулей в проекте нет.
`theme/global.css` держит только умолчания элементов (body, заголовки, ссылки, фокус, выделение, reduced motion),
`theme/app.css` — Tailwind, токены, шрифты и keyframes эффектов. Стили контролов MapLibre — `MAP_CONTROLS_CLASS`
в `features/map/mapStyle.ts` (его же использует карта точки в форме публикации).

### 9.7 Проверка на своём порту и грабли

```bash
cd frontend
pnpm dev --port 5181 --strictPort &         # свой порт, чтобы не мешать соседям
E2E_BASE_URL=http://localhost:5181 pnpm e2e  # API :8000 и демо-БД общие
```

- Подписи иконок-кнопок, `aria-label` и `data-testid` из раздела 7 сохраняются; `Select`, `Tabs`, `Dialog` на Radix дают те же роли, что давал Mantine.
- Закрытие диалога идёт с анимацией (около 100 мс): в тестах ждите исчезновения, а не фиксированной паузы.
- Список `Combobox` вынесен порталом из диалога, поэтому у него свой `onWheel`: иначе блокировка прокрутки диалога съедает колесо. Не убирайте.
- Радиусы почти прямоугольные: `rounded-xl` и `rounded-full` оставьте для точек, аватаров и пилюль.
- Новые зависимости этапа A: `tailwindcss`, `@tailwindcss/vite`, `tw-animate-css`, `shadcn` (только CSS `shadcn/tailwind.css`), `radix-ui`,
  `class-variance-authority`, `clsx`, `tailwind-merge`, `sonner`, `react-day-picker`, `date-fns`, `react-hook-form`, `zod`, `@hookform/resolvers`,
  `motion`, `@fontsource-variable/tektur`. Новые пакеты с `import` из `node_modules` добавляйте в `optimizeDeps.include` в `vite.config.ts`.

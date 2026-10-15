# UI: тема Fatality на Tailwind v4 + shadcn/ui (контракт переезда)

Решение пользователя от 13.10.2026. Оно заменяет D16 (раньше была нейтральная светлая тема): единственная тёмная тема
в стиле чит-меню Fatality. Frontend полностью переезжает с Mantine на Tailwind v4 + shadcn/ui. Поведение, тексты,
роли и `data-testid` не меняются — меняется только вид. Страховка — e2e `frontend/e2e` (Playwright): набор зелёный
до переезда и обязан быть зелёным после.

## 1. Принципы

- Одна тёмная тема: глубокий индиго, не чёрный. Плотные панели с тонкой рамкой и заголовками капсом, мелкие
  контролы, акцент — ярко-розовый.
- Розовый — только бренд и интерактив: активная вкладка, основная кнопка, включённый контрол, фокус, выделение.
- Цвета зон — только для зон. Красная зона (`#ff4d3d`, оттенок ~5°) всегда отличима от розового акцента
  (`#f0035b`, ~340°), а зона всегда подписана словом, не только цветом.
- Эффекты (свечение, анимации) — точечно: логин, логотип, счётчики, красная зона, «островок». Таблицы и формы
  остаются спокойными. Все эффекты уважают `prefers-reduced-motion`.

## 2. Стек

| Что | Чем |
|---|---|
| Стили | Tailwind CSS 4.3 (`@tailwindcss/vite`), конфигурация в CSS (`@theme`) |
| Примитивы | shadcn/ui (CLI `shadcn@latest`, база Radix: `init -b radix`), компоненты в `src/components/ui/` |
| `cn` | `src/lib/utils.ts` (clsx + tailwind-merge или пакет `cn`, как сгенерирует CLI) |
| Иконки | `@tabler/icons-react` — одна библиотека иконок (в `components.json` `iconLibrary: "tabler"`, lucide не тянуть, если CLI позволяет; иначе заменить импорты в сгенерированных файлах) |
| Тосты | `sonner` (обёртка вместо `notifications.show`) |
| Подтверждение | `AlertDialog` (обёртка вместо `modals.openConfirmModal`, тот же API `lib/confirm.tsx`) |
| Даты | `react-day-picker` 10 + `date-fns` 4 (локали `ru`, `kk`): компоненты `DateInput` и `DateTimeInput` поверх `calendar` + `popover` |
| Формы | `react-hook-form` + `zod` + `@hookform/resolvers` + shadcn `field` (вместо `@mantine/form`) |
| Хуки | `src/lib/hooks.ts`: `useDebouncedValue`, `useDebouncedCallback`, `useDisclosure`, `useElementSize`, `useReducedMotion` (вместо `@mantine/hooks`) |
| Анимации эффектов | `motion` (только для эффектов, которым он нужен) |
| Шрифт | Tektur (`@fontsource-variable/tektur`, OFL-1.1) везде, включая казахский (все буквы Ә Ғ Қ Ң Ө Ұ Ү Һ І и ₸ есть) |

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
| `--font-sans` | `'Tektur Variable', system-ui, sans-serif` | всё |
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
  Tektur, «SAQ» белым, «QURYLYS» розовым, лёгкое свечение.

## 5. Эффекты

Источник — React Bits (MIT + Commons Clause, встраивание в приложение разрешено) и Magic UI (MIT). Код
копируется в `src/components/fx/` с комментарием-атрибуцией в начале файла; лицензии — в `THIRD_PARTY_NOTICES.md`.
Aceternity и 21st.dev не используются (неясная лицензия, нужен API-ключ).

| Где | Эффект |
|---|---|
| Фон логина | React Bits **Aurora** (розовый, фиолетовый, индиго), пауза вне экрана |
| Логотип на логине | React Bits **GlitchText** (перекрашен в розовый), статичный при reduced motion |
| Счётчики зон, балл в карточке | React Bits **CountUp** |
| Карточка объекта красной зоны, строка списка | React Bits **BorderGlow** (розово-красное свечение рамки по курсору), спокойно в покое |
| «Островок» при событии | React Bits **StarBorder** по контуру пилюли |

## 6. Карта и граф

- Подложка: OpenFreeMap `https://tiles.openfreemap.org/styles/dark` (один источник `features/map/mapStyle.ts`, его же
  использует `features/ads/PointMap.tsx`), после `style.load` перекраска слоёв в палитру: фон `#0f0c20`, вода
  `#14112f`, парки `#161232`, жилая застройка/здания чуть светлее фона, границы `#3a3170`, подписи `#8d87b8` с ореолом
  фона. Запасной растровый стиль затемняется paint-свойствами `raster-brightness-max`, `raster-saturation`.
- Граф: палитра из токенов (`--graph-developer` для застройщиков, розовое кольцо — только выделение).

## 7. Правила переноса

1. Не менять поведение, запросы, i18n-ключи и тексты, роли и права, URL.
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
| C. Финал | ведущий | удалить Mantine, эффекты, атрибуции, README/SPEC, скриншоты, e2e целиком |

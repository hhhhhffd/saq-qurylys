import { mkdir, writeFile } from 'node:fs/promises';
import { expect, test } from '../support/test';
import type { Page, Route } from '@playwright/test';
import type { AdDetail, ObjectDetail, Role, SignalDetail, SignalRecipient, SignalStatus, User } from '../../src/api/types';

const screenshotDir = '/tmp/saq-ui-after';
const objectRow = {
  id: 7,
  code: 'D-07',
  name: 'ЖК Северный бриз',
  developer_name: 'ТОО Северстрой',
  score: 42,
  zone: 'yellow' as const,
  key_status: 'active_ads' as const,
  key_status_detail: null,
  district_name: 'Алматы ауданы',
  lat: 51.15,
  lon: 71.42,
  is_demo: false,
};

const dashboard = {
  counts: { green: 0, yellow: 1, red: 1, unscored: 0, total: 2 },
  last_updated_at: '2026-10-15T10:00:00Z',
  objects: [
    { ...objectRow, id: 9, code: 'D-09', name: 'ЖК Радужный парк', score: 72, zone: 'red' as const },
  ],
};

function makeUser(role: Role): User {
  return {
    id: role === 'mio_officer' ? 1 : role === 'gask' ? 2 : role === 'law_enforcement' ? 3 : 4,
    username: `mock_${role}`,
    full_name: role === 'mio_officer' ? 'Сотрудник МИО' : role === 'gask' ? 'Сотрудник ГАСК' : 'Сотрудник',
    role,
    territory_id: 1,
    locale: 'ru',
  };
}

function makeSignal(status: SignalStatus = 'requires_confirmation', recipient: SignalRecipient | null = 'gask'): SignalDetail {
  return {
    id: 42,
    number: 'SIG-2026-0042',
    object_id: 7,
    object_name: objectRow.name,
    is_demo: false,
    zone: 'yellow',
    status,
    recipient,
    due_date: status === 'sent' ? '2026-10-25' : null,
    is_overdue: false,
    created_at: '2026-10-15T10:00:00Z',
    origin: 'manual',
    sections: {
      object_developer: {
        object_code: objectRow.code,
        object_name: objectRow.name,
        address: null,
        cadastral_number: null,
        land_purpose: null,
        developer_name: 'ТОО Северстрой',
        bin: null,
        director: null,
        founders: [],
      },
      risk_factors: [],
      legal_basis_status: 'confirmed',
      needs_check: [],
      is_demo: false,
      permit_checks: [],
      publications: [],
      scheme_payments: { payment_schemes: [], contract_types: [], confirmed_payments_note: '' },
      proposed_measures: [],
      route: { recipient, review_days: 10 },
      note: '',
    },
    review_days: 10,
    sent_at: status === 'sent' || status === 'responded' || status === 'closed' ? '2026-10-15T11:00:00Z' : null,
    sent_by: status === 'sent' || status === 'responded' || status === 'closed' ? 1 : null,
    sent_pdf_evidence_id: null,
    return_comment: null,
    response_text: status === 'responded' || status === 'closed' ? 'Проверка проведена, меры приняты.' : null,
    response_at: status === 'responded' || status === 'closed' ? '2026-10-16T11:00:00Z' : null,
    responded_by: status === 'responded' || status === 'closed' ? 2 : null,
    created_by: 1,
    audit: [],
  };
}

const adFixture: AdDetail = {
  id: 11,
  territory_id: 1,
  source_account_id: null,
  platform: 'instagram',
  url: 'https://example.invalid/post/11',
  author: '@sever_build',
  published_at: '2026-10-14T10:00:00Z',
  captured_at: '2026-10-15T10:00:00Z',
  text: 'Бронирование квартир в ЖК Северный бриз. Рассрочка на 24 месяца, готовность 65%. Цена действует до сдачи дома.',
  phones: [],
  links: [],
  object_id: 7,
  object_name: objectRow.name,
  link_confidence: 0.82,
  link_method: 'name',
  payment_schemes: [],
  claimed_readiness_pct: null,
  price_before_completion: false,
  llm_status: 'done',
  status: 'verification',
  max_phrase_weight: 4,
  total_phrase_weight: 7,
  is_outdoor: false,
  is_demo: false,
  lat: null,
  lon: null,
  last_checked_at: null,
  removed_detected_at: null,
  capture_status: 'done',
  capture_error: null,
  origin: 'collector',
  ocr_status: null,
  created_at: '2026-10-15T10:00:00Z',
  versions: [],
  original_captured_at: '2026-10-15T10:00:00Z',
  original_evidence: null,
  phrase_hits: [],
  evidence: [],
  llm_extraction: {
    findings: [{ category: 'booking', quote: 'Бронирование квартир', confidence: 0.91, uncertain: false }],
    payment_schemes: ['installment'],
    claimed_readiness_pct: 65,
    price_before_completion: true,
    confidence: 0.91,
    uncertain: false,
  },
  linked_object: { id: 7, code: objectRow.code, name: objectRow.name },
};

function makeObject(zone: 'green' | 'yellow' | 'red' = 'yellow', name = objectRow.name): ObjectDetail {
  const score = zone === 'red' ? 72 : zone === 'yellow' ? 42 : 12;
  return {
    id: 7,
    code: objectRow.code,
    territory_id: 1,
    district_id: null,
    district_name: objectRow.district_name,
    developer_id: null,
    name,
    aliases: [],
    address: null,
    cadastral_number: null,
    land_purpose: null,
    lat: objectRow.lat,
    lon: objectRow.lon,
    planned_completion: null,
    forecast_completion: null,
    construction_status: 'active',
    stalled_since: null,
    readiness_actual_pct: 30,
    readiness_claimed_pct: null,
    prior_violations: null,
    score,
    zone,
    key_status: 'active_ads',
    key_status_detail: null,
    last_scored_at: '2026-10-15T10:00:00Z',
    next_check_at: null,
    is_demo: false,
    developer: null,
    documents: [],
    inspections: [],
    complaints: [],
    linked_entities: [],
    ads_7d_count: 1,
    readiness_gap_pp: null,
    latest_score: {
      score,
      zone,
      zone_reasons: [],
      breakdown: { factors: [], needs_check: [], legal_basis_status: 'confirmed' },
      calculated_at: '2026-10-15T10:00:00Z',
      trigger: 'event',
    },
  };
}

interface CapturedMutation {
  method: string;
  path: string;
  body: unknown;
}

interface MockState {
  role: Role;
  signals: SignalDetail[];
  signal: SignalDetail;
  ad: AdDetail;
  object: ObjectDetail;
  ads: AdDetail[];
  failReturnedCount?: number;
}

interface Harness {
  state: MockState;
  mutations: CapturedMutation[];
  unexpected: string[];
  listRequests: URL[];
  pageErrors: string[];
  consoleErrors: string[];
  failedApiRequests: string[];
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installMocks(page: Page, role: Role, overrides: Partial<MockState> = {}): Promise<Harness> {
  const state: MockState = {
    role,
    signals: [],
    signal: makeSignal(),
    ad: structuredClone(adFixture),
    object: makeObject(),
    ads: [structuredClone(adFixture)],
    ...overrides,
  };
  const harness: Harness = { state, mutations: [], unexpected: [], listRequests: [], pageErrors: [], consoleErrors: [], failedApiRequests: [] };

  page.on('pageerror', (error) => harness.pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') harness.consoleErrors.push(message.text());
  });
  page.on('requestfailed', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/')) harness.failedApiRequests.push(request.url());
  });

  await page.addInitScript(() => {
    localStorage.setItem('saq_token', 'mock-ui-session');
    localStorage.setItem('saq_lang', 'ru');
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const method = request.method();
    const body = method === 'GET' || method === 'HEAD' ? null : request.postDataJSON();
    if (method !== 'GET') harness.mutations.push({ method, path, body });

    if (method === 'GET' && path === '/auth/me') return json(route, makeUser(state.role));
    if (method === 'GET' && path === '/notifications') return json(route, { items: [] });
    if (method === 'GET' && path === '/activity') return json(route, { items: [], cursor: 'mock-cursor', reset: false });
    if (method === 'GET' && path === '/settings') {
      return json(route, {
        review_days: 10,
        ad_window_days: 90,
        readiness_gap_pp: 20,
        significant_delay_days: 90,
        zone_yellow_min: 25,
        zone_red_min: 60,
        complaints_threshold: 3,
        stalled_days: 180,
        recheck_after_days: 90,
        link_confidence_threshold: 0.7,
        green_interval_days: 90,
        yellow_interval_days: 30,
        recipient_emails: { mio: [], gask: [], law_enforcement: [] },
      });
    }
    if (method === 'GET' && path === '/territories') return json(route, []);
    if (method === 'GET' && path === '/dashboard') return json(route, dashboard);
    if (method === 'GET' && path === '/signals') {
      harness.listRequests.push(url);
      if ((state.failReturnedCount ?? 0) > 0 && url.searchParams.get('status') === 'returned') {
        state.failReturnedCount = (state.failReturnedCount ?? 0) - 1;
        return json(route, { detail: 'temporary fixture failure' }, 503);
      }
      const status = url.searchParams.get('status');
      const objectId = Number(url.searchParams.get('object_id')) || null;
      const rows = state.signals.filter((signal) =>
        (status === null || signal.status === status) &&
        (objectId === null || signal.object_id === objectId) &&
        (state.role !== 'gask' || signal.recipient === 'gask') &&
        (state.role !== 'law_enforcement' || signal.recipient === 'law_enforcement'),
      );
      return json(route, { items: rows, total: rows.length });
    }
    if (method === 'GET' && path === '/signals/42') return json(route, state.signal);
    if (method === 'GET' && path === '/signals/88') return json(route, state.signal);
    if (method === 'GET' && /^\/objects\/\d+$/.test(path)) {
      return json(route, { ...state.object, id: Number(path.split('/').at(-1)) });
    }
    if (method === 'GET' && path === '/objects') {
      return json(route, { items: [objectRow, { ...objectRow, id: 8, code: 'D-08', name: 'ЖК Малахит' }], total: 2 });
    }
    if (method === 'GET' && path === '/ads') {
      return json(route, { items: state.ads, total: state.ads.length });
    }
    if (method === 'GET' && /^\/ads\/\d+$/.test(path)) return json(route, state.ad);
    if (method === 'GET' && path === '/source-accounts') {
      return json(route, {
        items: [{
          id: 3,
          platform: 'aggregator',
          handle: 'ЖК Северный бриз · объявления OLX',
          url: 'https://www.olx.kz/search-example',
          object_id: 7,
          developer_id: null,
          territory_id: null,
          is_watched: true,
          last_collected_at: null,
          last_error: null,
          last_error_at: null,
        }],
      });
    }
    if (method === 'GET' && path === '/source-accounts/collectors') {
      return json(route, [
        { platform: 'instagram', enabled: false, sources: {} },
        { platform: 'telegram', enabled: false, sources: {} },
        { platform: 'aggregator', enabled: false, sources: { olx: false, krisha: false } },
      ]);
    }

    if (method === 'POST' && path === '/ads/11/accept-llm') return json(route, state.ad);
    if (method === 'PATCH' && path === '/ads/11') {
      state.ad = { ...state.ad, ...(body as Partial<AdDetail>) };
      return json(route, state.ad);
    }
    if (method === 'POST' && path === '/signals/42/confirm-and-send') {
      state.signal = { ...state.signal, status: 'sent', sent_at: '2026-10-16T12:00:00Z', sent_by: 1 };
      return json(route, state.signal);
    }
    if (method === 'POST' && path === '/signals/42/response') {
      const responseText = (body as { response_text: string }).response_text;
      state.signal = {
        ...state.signal,
        status: 'responded',
        response_text: responseText,
        response_at: '2026-10-16T13:00:00Z',
        responded_by: 2,
      };
      return json(route, state.signal);
    }
    if (method === 'POST' && path === '/signals/42/close') {
      state.signal = { ...state.signal, status: 'closed' };
      return json(route, state.signal);
    }
    if (method === 'POST' && path === '/signals') {
      state.signal = makeSignal('requires_confirmation', 'gask');
      state.signal.id = 88;
      state.signal.number = 'SIG-2026-0088';
      return json(route, state.signal, 201);
    }

    const descriptor = `${method} ${path}${url.search}`;
    harness.unexpected.push(descriptor);
    return json(route, { detail: `No UI fixture for ${descriptor}` }, 501);
  });
  return harness;
}

async function screenshot(page: Page, name: string) {
  await mkdir(screenshotDir, { recursive: true });
  await page.screenshot({ path: `${screenshotDir}/${name}.png`, fullPage: true });
}

function expectCleanBrowser(harness: Harness) {
  expect(harness.unexpected).toEqual([]);
  expect(harness.pageErrors).toEqual([]);
  expect(harness.consoleErrors).toEqual([]);
  expect(harness.failedApiRequests).toEqual([]);
}

test('work opens as the operator task queue, links the real next item and supports Kazakh', async ({ page }) => {
  const returned = makeSignal('returned', 'gask');
  returned.id = 43;
  returned.number = 'SIG-2026-0043';
  const confirmation = makeSignal('requires_confirmation', 'gask');
  const harness = await installMocks(page, 'mio_officer', {
    signals: [returned, confirmation, makeSignal('responded', 'gask'), makeSignal('sent', 'gask')],
  });

  await page.goto('/');
  await expect(page).toHaveURL(/\/work$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Задачи' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Доработать карточку SIG-2026-0043' })).toHaveAttribute('href', '/signals/43');
  await expect(page.getByRole('heading', { name: 'Путь работы' })).toBeVisible();
  await screenshot(page, 'work-mio-ru');

  await page.getByText('ҚАЗ', { exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'kk');
  await expect(page.getByRole('heading', { level: 1, name: 'Тапсырмалар' })).toBeVisible();
  await screenshot(page, 'work-mio-kk');
  expect(harness.mutations).toEqual([]);
  expectCleanBrowser(harness);
});

test('administrator opens the read-only task overview and recipient is kept out of registry work', async ({ page }) => {
  const adminHarness = await installMocks(page, 'admin', { signals: [makeSignal('requires_confirmation', 'gask')] });
  await page.goto('/');
  await expect(page).toHaveURL(/\/work$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Рабочий обзор' })).toBeVisible();
  await expect(page.getByText('Режим просмотра: выполнять действия по карточкам нельзя.')).toBeVisible();
  const openCards = page.getByRole('link', { name: 'Открыть карточки' });
  await expect(openCards).toHaveAttribute('href', '/signals');
  await screenshot(page, 'work-admin-readonly');
  await openCards.click();
  await expect(page).toHaveURL(/\/signals$/);
  const row = page.getByRole('row').filter({ hasText: 'SIG-2026-0042' });
  await expect(row).toContainText('Просмотр карточки');
  await expect(page.getByRole('button', { name: 'Создать карточку' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Подтвердить и направить' })).toHaveCount(0);
  expect(adminHarness.mutations).toEqual([]);
  expectCleanBrowser(adminHarness);

  const recipientHarness = await installMocks(page, 'gask');
  await page.goto('/');
  await expect(page).toHaveURL(/\/signals$/);
  await page.goto('/work');
  await expect(page).toHaveURL(/\/signals$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Карточки проверок' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Создать карточку' })).toHaveCount(0);
  expect(recipientHarness.mutations).toEqual([]);
  expectCleanBrowser(recipientHarness);
});

test('mobile object next-step anchors clear the sticky header and available signal action is explicit', async ({ page }) => {
  const longName = `ЖК Северный бриз — ${'очень длинное название объекта '.repeat(5)}`;
  const harness = await installMocks(page, 'mio_officer', { object: makeObject('yellow', longName) });
  const measures: Array<{ width: number; headerBottom: number; targetTop: number; gap: number }> = [];

  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/objects/7');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('ЖК Северный бриз');
    await expect(page.getByRole('button', { name: 'Создать карточку вручную' })).toBeVisible();
    if (width === 390) {
      await page.keyboard.press('Tab');
      await expect(page.getByRole('link', { name: 'SAQ QURYLYS' })).toBeFocused();
    }
    const anchor = page.getByRole('link', { name: 'К причинам оценки' });
    await anchor.click();
    await expect(page).toHaveURL(/#risk$/);
    const measurement = await page.evaluate(() => {
      const header = document.querySelector('header');
      const target = document.querySelector('#risk');
      if (!header || !target) throw new Error('Missing sticky header or #risk anchor');
      const headerBottom = header.getBoundingClientRect().bottom;
      const targetTop = target.getBoundingClientRect().top;
      return { headerBottom, targetTop, gap: targetTop - headerBottom };
    });
    measures.push({ width, ...measurement });
    expect.soft(measurement.targetTop, `#risk must clear the sticky header at ${width}px`).toBeGreaterThanOrEqual(measurement.headerBottom);
    const pageWidth = await page.evaluate(() => ({ inner: window.innerWidth, scroll: document.documentElement.scrollWidth }));
    expect.soft(pageWidth.scroll, `long object names must not cause horizontal overflow at ${width}px`).toBeLessThanOrEqual(pageWidth.inner);
    if (width === 390) await screenshot(page, 'object-mobile-390-risk');
  }

  await writeFile(`${screenshotDir}/object-anchor-offsets.json`, JSON.stringify(measures, null, 2));
  await test.info().attach('object-anchor-offsets.json', {
    body: Buffer.from(JSON.stringify(measures, null, 2)),
    contentType: 'application/json',
  });
  expect(harness.mutations).toEqual([]);
  expectCleanBrowser(harness);
});

test('object review reuses an open card, suppresses creation on stale lookup, and retries safely', async ({ page }) => {
  const active = makeSignal('returned', 'gask');
  active.number = 'SIG-OPEN-7';
  const existing = await installMocks(page, 'mio_officer', { signals: [active] });
  await page.goto('/objects/7');
  await expect(page.getByText(/уже есть открытая карточка проверки SIG-OPEN-7/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Открыть карточку проверки' })).toHaveAttribute('href', '/signals/42');
  await expect(page.getByRole('button', { name: 'Создать карточку вручную' })).toHaveCount(0);
  expect(existing.mutations).toEqual([]);
  expectCleanBrowser(existing);

  const failed = await installMocks(page, 'mio_officer', { failReturnedCount: 2 });
  await page.goto('/objects/7');
  await expect(page.getByRole('alert').filter({ hasText: 'Не удалось проверить карточки объекта' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Создать карточку вручную' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Проверить снова' }).click();
  await expect(page.getByRole('button', { name: 'Создать карточку вручную' })).toBeVisible();
  expect(failed.listRequests.filter((url) => url.searchParams.get('status') === 'returned')).toHaveLength(3);
  expect(failed.mutations).toEqual([]);
  expect(failed.unexpected).toEqual([]);
  expect(failed.pageErrors).toEqual([]);
  expect(failed.failedApiRequests).toEqual([]);
  expect(failed.consoleErrors).toEqual([
    'Failed to load resource: the server responded with a status of 503 (Service Unavailable)',
    'Failed to load resource: the server responded with a status of 503 (Service Unavailable)',
  ]);
  await screenshot(page, 'object-review-retried');
});

test('ad review makes AI scope visible, confirms the match and reports object-link changes', async ({ page }) => {
  const harness = await installMocks(page, 'mio_officer');
  await page.goto('/ads?ad=11');
  await expect(page.getByRole('article', { name: 'Публикация №11' })).toBeVisible();
  const aiPanel = page.getByRole('region', { name: 'Подсказки ИИ' });
  await expect(aiPanel).toBeVisible();
  await expect(aiPanel.getByText('Схемы оплаты', { exact: true })).toBeVisible();
  await expect(aiPanel.getByText('Рассрочка', { exact: true })).toBeVisible();
  await expect(aiPanel.getByText('Готовность', { exact: true })).toBeVisible();
  await expect(aiPanel.getByText('65%', { exact: true })).toBeVisible();
  await expect(aiPanel.getByText('Цена до сдачи', { exact: true })).toBeVisible();
  await expect(aiPanel.getByText('заявление найдено', { exact: true })).toBeVisible();
  await screenshot(page, 'ads-llm-before-review');

  await page.getByRole('button', { name: 'Подтвердить сведения ИИ' }).click();
  await expect(aiPanel.getByRole('status').filter({ hasText: /Сохранено то, что подтверждает текст/ })).toBeVisible();
  await expect(aiPanel.getByRole('status')).toContainText('Проверьте связь и откройте объект.');
  await expect.poll(() => harness.mutations.some((item) => item.path === '/ads/11/accept-llm')).toBe(true);
  expect(harness.mutations.filter((item) => item.method === 'POST' && item.path === '/ads/11/accept-llm')).toHaveLength(1);

  await page.getByRole('button', { name: 'Подтвердить связь' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Связь подтверждена.' })).toBeVisible();
  const confirmed = harness.mutations.find((item) => item.method === 'PATCH' && item.path === '/ads/11');
  expect(confirmed?.body).toEqual({ status: 'captured' });

  await page.getByRole('button', { name: 'Изменить объект' }).click();
  const objectSelect = page.getByRole('combobox', { name: 'Объект' }).last();
  await objectSelect.fill('Малахит');
  await page.getByRole('option', { name: /D-08 · ЖК Малахит/ }).click();
  await page.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Привязка сохранена. Сверьте, что публикация относится к выбранному объекту.' })).toBeVisible();
  const linkMutation = harness.mutations.find((item) => item.method === 'PATCH' && item.path === '/ads/11' && (item.body as { object_id?: number }).object_id === 8);
  expect(linkMutation?.body).toEqual({ object_id: 8 });
  await screenshot(page, 'ads-llm-object-confirmed');
  expectCleanBrowser(harness);
});

test('disabled collectors route staff to manual ad entry without starting a collector', async ({ page }) => {
  const harness = await installMocks(page, 'mio_officer', { ads: [] });
  await page.goto('/sources');
  await expect(page.getByText(/Автоматический сбор включён для 0 из 4 платформ/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Собрать сейчас' })).toBeDisabled();
  await expect(page.getByRole('link', { name: 'Добавить рекламу по ссылке или вручную' })).toHaveAttribute('href', '/ads');
  await page.getByRole('link', { name: 'Добавить рекламу по ссылке или вручную' }).click();
  await expect(page).toHaveURL(/\/ads$/);
  await expect(page.getByText('Рекламных публикаций пока нет')).toBeVisible();
  await page.getByRole('button', { name: 'Добавить вручную' }).first().click();
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Добавить публикацию вручную' })).toBeVisible();
  await screenshot(page, 'ads-manual-entry');
  expect(harness.mutations).toEqual([]);
  expectCleanBrowser(harness);
});

test('recipient filters stay role-aware; send, answer and close each have explicit next steps', async ({ page }) => {
  const signal = makeSignal('requires_confirmation', 'gask');
  const harness = await installMocks(page, 'mio_officer', { signal, signals: [signal] });

  await page.goto('/signals/42');
  await expect(page.getByRole('heading', { level: 2, name: 'Проверьте факты и получателя' })).toBeVisible();
  await page.getByRole('button', { name: 'Подтвердить и направить' }).click();
  const sendDialog = page.getByRole('dialog', { name: 'Подтвердить и направить' });
  await expect(sendDialog).toBeVisible();
  await expect(sendDialog.getByText('Перед отправкой проверьте адресата, срок и последствия.')).toBeVisible();
  await expect(sendDialog.getByText(/После направления редактирование карточки будет заблокировано/)).toBeVisible();
  await sendDialog.getByRole('button', { name: 'Подтвердить и направить' }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Карточка направлена — ожидаем ответ' })).toBeVisible();
  const sendMutation = harness.mutations.find((item) => item.path === '/signals/42/confirm-and-send');
  expect(sendMutation?.body).toEqual({ recipient: 'gask' });
  await screenshot(page, 'signal-sent-next-step');

  harness.state.role = 'gask';
  await page.reload();
  await expect(page.getByRole('heading', { level: 2, name: 'Внесите результат рассмотрения' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Внести результат' })).toBeVisible();
  await page.getByRole('button', { name: 'Внести результат' }).click();
  const responseDialog = page.getByRole('dialog', { name: 'Внести результат' });
  await responseDialog.getByLabel('Результат рассмотрения').fill('Проверка проведена, меры приняты.');
  await responseDialog.getByRole('button', { name: 'Внести результат' }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Ответ передан сотруднику МИО' })).toBeVisible();
  expect(harness.mutations.find((item) => item.path === '/signals/42/response')?.body).toEqual({
    response_text: 'Проверка проведена, меры приняты.',
  });
  await expect(page.getByRole('button', { name: 'Закрыть карточку' })).toHaveCount(0);

  harness.state.role = 'mio_officer';
  await page.reload();
  await expect(page.getByRole('heading', { level: 2, name: 'Проверьте ответ и закройте карточку' })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть карточку' }).click();
  const closeDialog = page.getByRole('dialog', { name: 'Закрыть карточку' });
  await expect(closeDialog).toBeVisible();
  await expect(closeDialog.getByText(/Карточка SIG-2026-0042 будет закрыта/)).toBeVisible();
  await closeDialog.getByRole('button', { name: 'Закрыть карточку' }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Проверка завершена' })).toBeVisible();
  expect(harness.mutations.filter((item) => item.path === '/signals/42/close')).toHaveLength(1);

  await page.goto('/signals?status=responded&object_id=7&page=3');
  const list = page.getByRole('group', { name: 'Этап карточки' });
  await expect(list.getByRole('button', { name: 'Ответ получен' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('combobox', { name: 'Объект' })).toBeVisible();
  await expect.poll(() => harness.listRequests.some((url) =>
    url.searchParams.get('status') === 'responded' && url.searchParams.get('object_id') === '7' && url.searchParams.get('offset') === '50',
  )).toBe(true);

  harness.state.role = 'gask';
  await page.reload();
  await expect(page.getByRole('group', { name: 'Этап карточки' }).getByRole('button', { name: 'Ответ получен' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('combobox', { name: 'Объект' })).toHaveCount(0);
  await expect.poll(() => harness.listRequests.slice(-1)[0]?.searchParams.has('object_id')).toBe(false);
  await page.getByRole('button', { name: 'Сбросить фильтры' }).click();
  await expect(page).toHaveURL(/\/signals$/);
  expect(harness.mutations.every((item) => item.path.startsWith('/signals/42/'))).toBe(true);
  expectCleanBrowser(harness);
});

test('signal creation runs once after a successful object lookup and navigates to the new card', async ({ page }) => {
  const harness = await installMocks(page, 'mio_officer', { object: makeObject('green') });
  await page.goto('/objects/7');
  await expect(page.getByText(/По текущей оценке дополнительных задач нет/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Создать карточку вручную' })).toBeVisible();
  await page.getByRole('button', { name: 'Создать карточку вручную' }).click();
  await expect(page).toHaveURL(/\/signals\/88$/);
  expect(harness.mutations.filter((item) => item.method === 'POST' && item.path === '/signals')).toHaveLength(1);
  expect(harness.mutations.find((item) => item.path === '/signals')?.body).toEqual({ object_id: 7 });
  await screenshot(page, 'signal-created-from-object');
  expectCleanBrowser(harness);
});

test('signal URL filters clear status, object and page together', async ({ page }) => {
  const harness = await installMocks(page, 'mio_officer');
  await page.goto('/signals?status=responded&object_id=7&page=3');
  await expect(page.getByRole('button', { name: 'Сбросить фильтры' })).toBeVisible();
  await page.getByRole('button', { name: 'Сбросить фильтры' }).click();
  await expect(page).toHaveURL(/\/signals$/);
  await expect.poll(() => harness.listRequests.some((url) =>
    url.searchParams.get('status') === 'responded' && url.searchParams.get('object_id') === '7' && url.searchParams.get('offset') === '50',
  )).toBe(true);
  await expect.poll(() => harness.listRequests.some((url) =>
    !url.searchParams.has('status') && !url.searchParams.has('object_id') && url.searchParams.get('offset') === '0',
  )).toBe(true);
  expect(harness.mutations).toEqual([]);
  expectCleanBrowser(harness);
});

test('a sent card addressed to MIO is shown as an operator response task', async ({ page }) => {
  const sentToMio = makeSignal('sent', 'mio');
  const harness = await installMocks(page, 'mio_officer', { signals: [sentToMio] });
  await page.goto('/work');
  await expect(page.getByRole('link', { name: 'Внести результат по карточке SIG-2026-0042' })).toHaveAttribute('href', '/signals/42');
  await screenshot(page, 'work-mio-sent-to-mio');
  expect(harness.mutations).toEqual([]);
  expectCleanBrowser(harness);
});

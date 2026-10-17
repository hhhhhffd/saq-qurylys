import { mkdir, writeFile } from 'node:fs/promises';
import { expect, test } from '../support/test';
import type { Page, Route } from '@playwright/test';
import type { ActivityEvent, AdDetail, EvidenceMeta, ObjectDetail, ObjectDocument, Role, SignalDetail, SignalRecipient, SignalStatus, User } from '../../src/api/types';

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

const registryShaA = 'a'.repeat(64);
const registryShaB = 'b'.repeat(64);

function registryResponseJson(name: string, warrantyNumber: string): string {
  const payload = {
    success: true,
    message: 'Object Details retrieved successfully',
    data: {
      basicData: {
        name,
        address: 'г. Учебный, ул. Примерная, 1',
        authority: { id: 1, name: 'Орган выдачи тестовых гарантий' },
        warranty_number: warrantyNumber,
        issue_date: '16.10.2026',
        start_date: '01.02.2025',
        commissioning_date: '01.09.2026',
        city: { id: 1, name_ru: 'г. Учебный' },
        region: { id: 1, name_ru: 'Учебная область' },
        developerData: { bin: '000000000001', name: 'ТОО Учебный застройщик' },
      },
      objectData: { no_of_houses: '2', no_of_floors: '9', comfort_class: 'III класс' },
      locationData: { cadastral_number: '00-000-000-0000' },
      companyData: {},
    },
  };
  return JSON.stringify(payload).replace(/[\u007f-\uffff]/g, (character) =>
    `\\u${character.charCodeAt(0).toString(16).padStart(4, '0')}`,
  );
}

function makeEvidence(
  id: number,
  kind: EvidenceMeta['kind'],
  contentType: string,
  sha256: string,
  capturedAt: string,
): EvidenceMeta {
  return {
    id,
    kind,
    content_type: contentType,
    sha256,
    size_bytes: 512,
    captured_at: capturedAt,
    source_url: null,
    retention_until: null,
  };
}

function makeRegistryObject(): ObjectDetail {
  const evidence = [
    makeEvidence(5181, 'registry_response', 'application/json', registryShaA, '2026-10-14T09:00:00Z'),
    makeEvidence(5182, 'registry_response', 'application/json', registryShaA, '2026-10-15T10:00:00Z'),
    makeEvidence(5183, 'registry_response', 'application/json', registryShaB, '2026-10-16T11:00:00Z'),
    makeEvidence(5190, 'photo', 'image/png', 'c'.repeat(64), '2026-10-16T11:05:00Z'),
    makeEvidence(5191, 'pdf', 'application/pdf', 'd'.repeat(64), '2026-10-16T11:10:00Z'),
  ];
  const object = makeObject();
  const document: ObjectDocument = {
    id: 31,
    object_id: 7,
    doc_type: 'guarantee',
    number: 'ГАРАНТИЯ-ТЕСТ-002',
    issued_at: '2026-10-16',
    issuer: 'Тестовый реестр',
    check_status: 'confirmed',
    checked_at: '2026-10-16T11:15:00Z',
    checked_by: 1,
    check_source: 'housing_portal',
    note: null,
    evidence,
  };
  object.documents = [document];
  return object;
}

const transparentPng = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/qgAAAABJRU5ErkJggg==',
  'base64',
);

function registryContentFixtures() {
  return {
    5181: { contentType: 'application/json', body: registryResponseJson('ЖК Учебный дом', 'ГАРАНТИЯ-ТЕСТ-001') },
    5182: { contentType: 'application/json', body: registryResponseJson('ЖК Учебный дом', 'ГАРАНТИЯ-ТЕСТ-001') },
    5183: {
      contentType: 'application/json',
      body: registryResponseJson('ЖК Учебный дом · актуальные сведения', 'ГАРАНТИЯ-ТЕСТ-002'),
    },
    5190: { contentType: 'image/png', body: transparentPng },
    5191: { contentType: 'application/pdf', body: Buffer.from('%PDF-1.4\n% isolated UI fixture\n', 'utf8') },
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
  activityEvents?: ActivityEvent[];
  evidenceContents?: Record<number, { contentType: string; body: string | Buffer }>;
  evidenceFailures?: Record<number, number>;
  expectedEvidence503Responses: number;
  signal: SignalDetail;
  ad: AdDetail;
  object: ObjectDetail;
  ads: AdDetail[];
  failReturnedCount?: number;
  /** `/assistant/config` answers 404 when false (the module is off) */
  assistantEnabled?: boolean;
  /** SSE bodies of the next `/assistant/chat` requests, in order; the default reply afterwards */
  assistantReplies?: string[];
  /** `/assistant/chat` never answers, so the Stop button can be tested */
  assistantHangs?: boolean;
}

const sse = (events: object[]) => events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');

const assistantReply = sse([
  { type: 'sources', sources: [{ id: 'zones', title: 'Зоны риска', page: '/work' }, { id: 'terms', title: 'Термины', page: null }] },
  { type: 'tool', name: 'search_objects', label: 'Ищу объекты: Северный' },
  { type: 'delta', text: 'Объект [ЖК Северный бриз](/objects/7) в **жёлтой** зоне.\n\n- пункт один\n' },
  { type: 'delta', text: '- пункт два\n\nСм. [документацию](https://example.invalid/doc).' },
  { type: 'done' },
]);

interface Harness {
  state: MockState;
  mutations: CapturedMutation[];
  unexpected: string[];
  listRequests: URL[];
  evidenceRequests: Array<{ id: number; authorization: string | null }>;
  expectedCancelledEvidenceIds: Set<number>;
  pageErrors: string[];
  consoleErrors: string[];
  failedApiRequests: Array<{ url: string; errorText: string }>;
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installMocks(page: Page, role: Role, overrides: Partial<MockState> = {}): Promise<Harness> {
  const state: MockState = {
    role,
    signals: [],
    expectedEvidence503Responses: 0,
    signal: makeSignal(),
    ad: structuredClone(adFixture),
    object: makeObject(),
    ads: [structuredClone(adFixture)],
    ...overrides,
  };
  const harness: Harness = {
    state,
    mutations: [],
    unexpected: [],
    listRequests: [],
    evidenceRequests: [],
    expectedCancelledEvidenceIds: new Set(),
    pageErrors: [],
    consoleErrors: [],
    failedApiRequests: [],
  };

  page.on('pageerror', (error) => harness.pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') harness.consoleErrors.push(message.text());
  });
  page.on('requestfailed', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/v1/')) {
      harness.failedApiRequests.push({ url: request.url(), errorText: request.failure()?.errorText ?? 'unknown failure' });
    }
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
    if (method === 'GET' && path === '/activity') {
      return json(route, { items: state.activityEvents ?? [], cursor: 'mock-cursor', reset: false });
    }
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
    if (method === 'GET' && path === '/assistant/config') {
      return state.assistantEnabled === false
        ? json(route, { detail: { code: 'not_found', message: 'Assistant is off' } }, 404)
        : json(route, { enabled: true, model: 'test' });
    }
    if (method === 'POST' && path === '/assistant/chat') {
      if (state.assistantHangs) return new Promise<void>(() => undefined);
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: state.assistantReplies?.shift() ?? assistantReply });
    }
    if (method === 'GET' && path === '/vision/config') {
      return json(route, {
        enabled: false,
        detector_mode: 'disabled',
        detector_model: null,
        ocr_enabled: false,
        max_photo_mb: 20,
        max_video_mb: 200,
        max_duration_seconds: 600,
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
    const evidenceMatch = /^\/evidence\/(\d+)\/content$/.exec(path);
    if (method === 'GET' && evidenceMatch) {
      const id = Number(evidenceMatch[1]);
      harness.evidenceRequests.push({ id, authorization: request.headers()['authorization'] ?? null });
      const remainingFailures = state.evidenceFailures?.[id] ?? 0;
      if (remainingFailures > 0) {
        if (state.evidenceFailures) state.evidenceFailures[id] = remainingFailures - 1;
        state.expectedEvidence503Responses += 1;
        return json(route, { detail: 'temporary evidence fixture failure' }, 503);
      }
      const content = state.evidenceContents?.[id];
      if (content) return route.fulfill({ status: 200, contentType: content.contentType, body: content.body });
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
  const fixture503ConsoleErrors = harness.consoleErrors.filter((message) =>
    message === 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)',
  );
  expect(fixture503ConsoleErrors.length).toBeLessThanOrEqual(harness.state.expectedEvidence503Responses);
  expect(harness.consoleErrors.filter((message) =>
    message !== 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)',
  )).toEqual([]);
  const unexplainedFailures = harness.failedApiRequests.filter((failure) => {
    const evidenceId = /\/api\/v1\/evidence\/(\d+)\/content(?:\?|$)/.exec(failure.url)?.[1];
    return !(
      failure.errorText === 'net::ERR_ABORTED' &&
      evidenceId !== undefined &&
      harness.expectedCancelledEvidenceIds.has(Number(evidenceId))
    );
  });
  expect(unexplainedFailures).toEqual([]);
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

test('header restores the compact style and keeps utilities usable at every supported width', async ({ page }) => {
  const harness = await installMocks(page, 'mio_officer');
  await page.goto('/work');
  const header = page.getByRole('banner');
  const utilities = page.getByRole('group', { name: 'Действия и настройки' });
  const typography = await page.evaluate(() => {
    const headerElement = document.querySelector('header');
    const navigation = headerElement?.querySelector('nav');
    const activeLink = navigation?.querySelector<HTMLAnchorElement>('a[aria-current="page"]');
    if (!activeLink) throw new Error('Missing active navigation link');
    const navStyle = getComputedStyle(activeLink);
    return {
      bodyFontSize: getComputedStyle(document.body).fontSize,
      navFontFamily: navStyle.fontFamily,
      navTextTransform: navStyle.textTransform,
      navTextShadow: navStyle.textShadow,
    };
  });
  expect(typography.bodyFontSize).toBe('14px');
  expect(typography.navFontFamily.toLowerCase()).toContain('tektur variable');
  expect(typography.navTextTransform).toBe('uppercase');
  expect(typography.navTextShadow).not.toBe('none');

  const breakpoints = [320, 390, 768, 1024, 1440];
  const measurements: Array<{
    width: number;
    headerHeight: number;
    clientWidth: number;
    scrollWidth: number;
    mobileNavLabels: Array<{ cell: number; label: string; left: number; right: number; cellLeft: number; cellRight: number }>;
  }> = [];
  const popoverMeasurements: Array<{ width: number; x: number; y: number; right: number; bottom: number }> = [];

  for (const width of breakpoints) {
    await page.setViewportSize({ width, height: 844 });
    await expect(header).toBeVisible();
    await expect(utilities).toBeVisible();
    await expect(page.getByText('Мониторинг', { exact: true })).toBeHidden();
    const languageBounds = await page.getByLabel('Язык').evaluate((frame) => {
      const frameRect = frame.getBoundingClientRect();
      return {
        frame: { left: frameRect.left, top: frameRect.top, right: frameRect.right, bottom: frameRect.bottom },
        buttons: Array.from(frame.querySelectorAll<HTMLElement>('[role="radio"]')).map((button) => {
          const rect = button.getBoundingClientRect();
          return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
        }),
      };
    });
    expect(languageBounds.frame.left, `language control must fit at ${width}px`).toBeGreaterThanOrEqual(0);
    expect(languageBounds.frame.right, `language control must fit at ${width}px`).toBeLessThanOrEqual(width);
    expect(languageBounds.frame.bottom - languageBounds.frame.top, `language frame at ${width}px`).toBeGreaterThanOrEqual(48);
    expect(languageBounds.buttons).toHaveLength(2);
    for (const button of languageBounds.buttons) {
      expect(button.left, `language button left at ${width}px`).toBeGreaterThanOrEqual(languageBounds.frame.left);
      expect(button.right, `language button right at ${width}px`).toBeLessThanOrEqual(languageBounds.frame.right);
      expect(button.top, `language button top at ${width}px`).toBeGreaterThanOrEqual(languageBounds.frame.top);
      expect(button.bottom, `language button bottom at ${width}px`).toBeLessThanOrEqual(languageBounds.frame.bottom);
    }
    const measurement = await page.evaluate(() => {
      const headerElement = document.querySelector('header');
      const navigation = headerElement?.querySelector('nav');
      const utilityGroup = headerElement?.querySelector('[role="group"][aria-label]');
      if (!headerElement || !navigation || !utilityGroup) throw new Error('Missing header region');

      const box = (element: Element) => {
        const rect = element.getBoundingClientRect();
        return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
      };
      const visible = (element: Element) => getComputedStyle(element).display !== 'none';
      const navigationBox = box(navigation);
      const utilityBox = box(utilityGroup);
      const utilityTargets = Array.from(utilityGroup.querySelectorAll<HTMLElement>('button,[role="radio"]'))
        .filter(visible)
        .map((target) => {
          const rect = target.getBoundingClientRect();
          return { width: rect.width, height: rect.height };
        });
      const mobileNavLabels = window.innerWidth <= 992
        ? Array.from(navigation.children).flatMap((cell, index) => {
          const label = Array.from(cell.querySelectorAll('span')).find((span) => visible(span) && span.textContent?.trim());
          if (!label) return [];
          const range = document.createRange();
          range.selectNodeContents(label);
          const textRect = range.getBoundingClientRect();
          const cellRect = cell.getBoundingClientRect();
          return [{
            cell: index,
            label: label.textContent?.trim() ?? '',
            left: textRect.left,
            right: textRect.right,
            cellLeft: cellRect.left,
            cellRight: cellRect.right,
          }];
        })
        : [];

      return {
        headerHeight: headerElement.getBoundingClientRect().height,
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        navigationBox,
        utilityBox,
        utilityHeight: utilityBox.bottom - utilityBox.top,
        utilityTargets,
        mobileNavLabels,
      };
    });
    measurements.push({ width, ...measurement });

    expect(measurement.scrollWidth, `header must not cause horizontal overflow at ${width}px`).toBeLessThanOrEqual(measurement.clientWidth);
    expect(measurement.utilityHeight, `utility toolbar must stay large enough at ${width}px`).toBeGreaterThanOrEqual(48);
    expect(measurement.utilityTargets.length, `all toolbar targets must be present at ${width}px`).toBeGreaterThan(3);
    for (const target of measurement.utilityTargets) {
      expect(target.width, `toolbar target width at ${width}px`).toBeGreaterThanOrEqual(44);
      expect(target.height, `toolbar target height at ${width}px`).toBeGreaterThanOrEqual(44);
    }
    if (width <= 992) {
      expect(measurement.mobileNavLabels, `all mobile navigation labels must be measured at ${width}px`).toHaveLength(5);
      for (const label of measurement.mobileNavLabels) {
        expect(label.left, `${label.label} must start inside its navigation cell at ${width}px`).toBeGreaterThanOrEqual(label.cellLeft - 0.5);
        expect(label.right, `${label.label} must end inside its navigation cell at ${width}px`).toBeLessThanOrEqual(label.cellRight + 0.5);
      }
      for (let index = 1; index < measurement.mobileNavLabels.length; index += 1) {
        const previous = measurement.mobileNavLabels[index - 1];
        const current = measurement.mobileNavLabels[index];
        expect(previous.right, `${previous.label} must not overlap ${current.label} at ${width}px`).toBeLessThanOrEqual(current.left + 0.5);
      }
    }

    if (width <= 992) {
      expect(measurement.headerHeight, `mobile header height at ${width}px`).toBeGreaterThanOrEqual(92);
      expect(measurement.headerHeight, `mobile header height at ${width}px`).toBeLessThanOrEqual(94);
    } else {
      expect(measurement.headerHeight, `desktop header height at ${width}px`).toBeGreaterThanOrEqual(56);
      expect(measurement.headerHeight, `desktop header height at ${width}px`).toBeLessThanOrEqual(58);
    }

    if (width === 1440 || width === 320) await screenshot(page, `header-${width}`);

    const bell = utilities.getByRole('button', { name: 'Уведомления' });
    await bell.focus();
    await page.keyboard.press('Enter');
    const notificationContent = page.getByText('Новых уведомлений нет', { exact: true });
    await expect(notificationContent).toBeVisible();
    expect(await notificationContent.evaluate((element) => getComputedStyle(element).fontSize)).toBe('13px');
    const popover = page.locator('[data-slot="popover-content"]');
    let previousPosition: { x: number; y: number } | null = null;
    await expect.poll(async () => {
      const box = await popover.boundingBox();
      if (!box) return false;
      const position = { x: Math.round(box.x), y: Math.round(box.y) };
      const stable = previousPosition?.x === position.x && previousPosition?.y === position.y;
      previousPosition = position;
      return stable;
    }).toBe(true);
    const popoverBox = await popover.boundingBox();
    const bellBox = await bell.boundingBox();
    expect(popoverBox).not.toBeNull();
    expect(bellBox).not.toBeNull();
    expect(popoverBox!.x).toBeGreaterThanOrEqual(0);
    expect(popoverBox!.x + popoverBox!.width).toBeLessThanOrEqual(width);
    expect(popoverBox!.y).toBeGreaterThanOrEqual(bellBox!.y + bellBox!.height - 1);
    popoverMeasurements.push({
      width,
      x: popoverBox!.x,
      y: popoverBox!.y,
      right: popoverBox!.x + popoverBox!.width,
      bottom: popoverBox!.y + popoverBox!.height,
    });
    if (width === 320) await screenshot(page, 'notifications-320-open');
    await page.keyboard.press('Escape');
    await expect(notificationContent).toBeHidden();
    await expect(bell).toBeFocused();

    const profile = utilities.getByRole('button', { name: 'Меню пользователя' });
    await profile.focus();
    await page.keyboard.press('Enter');
    const profileMenu = page.getByRole('menu');
    await expect(profileMenu).toBeVisible();
    const menuBox = await profileMenu.boundingBox();
    expect(menuBox).not.toBeNull();
    expect(menuBox!.x).toBeGreaterThanOrEqual(8);
    expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(width - 8);
    await page.keyboard.press('Escape');
    await expect(profileMenu).toBeHidden();
    await expect(profile).toBeFocused();
  }

  const kazakh = page.getByRole('radio', { name: 'ҚАЗ' });
  await kazakh.click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'kk');
  await expect(page.getByRole('group', { name: 'Әрекеттер мен баптаулар' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Хабарландырулар' })).toBeVisible();
  await page.getByRole('radio', { name: 'RU' }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'ru');

  const browser = page.context().browser();
  if (!browser) throw new Error('Missing browser for the unauthenticated login check');
  const loginContext = await browser.newContext({ viewport: { width: 320, height: 844 }, locale: 'ru-RU' });
  try {
    const loginPage = await loginContext.newPage();
    await loginPage.goto(new URL('/login', page.url()).toString());
    await expect(loginPage.getByRole('heading', { level: 1, name: 'Вход в систему' })).toBeVisible();
    const loginLanguageBounds = await loginPage.getByLabel('Язык').evaluate((frame) => {
      const frameRect = frame.getBoundingClientRect();
      return {
        frame: { left: frameRect.left, top: frameRect.top, right: frameRect.right, bottom: frameRect.bottom },
        buttons: Array.from(frame.querySelectorAll<HTMLElement>('[role="radio"]')).map((button) => {
          const rect = button.getBoundingClientRect();
          return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
        }),
      };
    });
    expect(loginLanguageBounds.frame.left).toBeGreaterThanOrEqual(0);
    expect(loginLanguageBounds.frame.right).toBeLessThanOrEqual(320);
    expect(loginLanguageBounds.frame.bottom - loginLanguageBounds.frame.top).toBeGreaterThanOrEqual(48);
    expect(loginLanguageBounds.buttons).toHaveLength(2);
    for (const button of loginLanguageBounds.buttons) {
      expect(button.left).toBeGreaterThanOrEqual(loginLanguageBounds.frame.left);
      expect(button.right).toBeLessThanOrEqual(loginLanguageBounds.frame.right);
      expect(button.top).toBeGreaterThanOrEqual(loginLanguageBounds.frame.top);
      expect(button.bottom).toBeLessThanOrEqual(loginLanguageBounds.frame.bottom);
    }
  } finally {
    await loginContext.close();
  }

  await writeFile(`${screenshotDir}/header-breakpoints.json`, JSON.stringify(measurements, null, 2));
  await writeFile(`${screenshotDir}/header-popover-bounds.json`, JSON.stringify(popoverMeasurements, null, 2));
  expect(harness.mutations).toEqual([]);
  expectCleanBrowser(harness);
});

test('activity notification opens below the sticky header and navigates to its event', async ({ page }) => {
  const event: ActivityEvent = {
    id: 'signal_created:ui-42',
    kind: 'signal_created',
    at: '2026-10-16T11:30:00Z',
    object_id: 7,
    object_name: objectRow.name,
    ad_id: null,
    signal_id: 42,
    origin: 'manual',
    platform: null,
    score_before: null,
    score_after: null,
    zone_before: null,
    zone_after: null,
    number: 'SIG-UI-0042',
    is_demo: false,
  };
  const harness = await installMocks(page, 'mio_officer', { activityEvents: [] });
  await page.setViewportSize({ width: 1440, height: 900 });
  const initialActivityPoll = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/activity');
  await page.goto('/work');
  await initialActivityPoll;
  harness.state.activityEvents = [event];

  const activity = page.getByRole('button', { name: /SIG-UI-0042/ });
  await expect(activity).toBeVisible();
  await expect(page.getByText('Мониторинг', { exact: true })).toBeHidden();
  await activity.hover();
  const liveRegion = page.getByTestId('activity-live-region');
  await expect(liveRegion).toHaveAttribute('aria-live', 'polite');
  await expect(liveRegion).toContainText('SIG-UI-0042');
  const metrics = await page.evaluate(() => {
    const header = document.querySelector('header');
    const island = header?.querySelector<HTMLElement>('[data-open="true"][data-place="below"]');
    if (!header || !island) throw new Error('Open activity island was not placed below the header');
    const headerRect = header.getBoundingClientRect();
    const islandRect = island.getBoundingClientRect();
    return {
      headerBottom: headerRect.bottom,
      islandLeft: islandRect.left,
      islandRight: islandRect.right,
      islandTop: islandRect.top,
      islandBottom: islandRect.bottom,
      viewportWidth: document.documentElement.clientWidth,
    };
  });
  expect(metrics.islandTop).toBeGreaterThanOrEqual(metrics.headerBottom + 7);
  expect(metrics.islandLeft).toBeGreaterThanOrEqual(16);
  expect(metrics.islandRight).toBeLessThanOrEqual(metrics.viewportWidth - 16);
  expect(metrics.islandBottom).toBeGreaterThan(metrics.islandTop);
  await screenshot(page, 'monitoring-activity-open');
  await activity.click();
  await expect(page).toHaveURL(/\/signals\/42$/);
  expect(harness.mutations).toEqual([]);
  expectCleanBrowser(harness);
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

test('registry answers show readable latest data, group identical captures and preserve file evidence', async ({ page }) => {
  const harness = await installMocks(page, 'mio_officer', {
    object: makeRegistryObject(),
    evidenceContents: registryContentFixtures(),
  });
  await page.goto('/objects/7');

  const registryAction = page.getByRole('button', { name: 'Открыть сохранённые сведения из реестра' });
  await expect(registryAction).toHaveCount(1);
  await expect(registryAction).toContainText('2 версии');

  const photo = page.getByRole('img', { name: 'Фото #5190' });
  await expect(photo).toBeVisible();
  await page.getByRole('button', { name: 'Фото #5190' }).click();
  const photoDialog = page.getByRole('dialog', { name: 'Фото #5190' });
  await expect(photoDialog.getByRole('img', { name: 'Фото #5190' })).toBeVisible();
  harness.expectedCancelledEvidenceIds.add(5190);
  await page.keyboard.press('Escape');
  await expect(photoDialog).toBeHidden();

  const pdfButton = page.getByRole('button', { name: 'PDF', exact: true });
  await expect(pdfButton).toBeVisible();
  const pdfResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/evidence/5191/content');
  await pdfButton.click();
  await pdfResponse;

  await registryAction.click();
  const dialog = page.getByRole('dialog', { name: 'Сведения из реестра' });
  await expect(dialog.getByText('ЖК Учебный дом · актуальные сведения', { exact: true })).toBeVisible();
  await expect(dialog.getByText('г. Учебный, ул. Примерная, 1', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Орган выдачи тестовых гарантий', { exact: true })).toBeVisible();
  await expect(dialog.getByText('ГАРАНТИЯ-ТЕСТ-002', { exact: true })).toBeVisible();
  await expect(dialog.getByText('ТОО Учебный застройщик', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Название объекта', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Основание', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Номер документа', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Дата выдачи', { exact: true })).toBeVisible();
  await expect(dialog.getByText('16.10.2026', { exact: true })).toBeVisible();
  await expect(dialog).not.toContainText('"success":true');
  await expect(dialog).not.toContainText('Object Details retrieved successfully');
  await expect(dialog.getByText(/Последняя сохранённая версия/)).toContainText('#5183');

  const versionSelect = dialog.getByLabel('Сохранённые версии');
  await expect(versionSelect).toHaveValue(`sha:${registryShaB}`);
  await expect(versionSelect.locator('option')).toHaveCount(2);
  const history = dialog.getByText('История сохранений (3)', { exact: true });
  await history.click();
  const historyList = dialog.locator('details').last();
  for (const id of [5181, 5182, 5183]) await expect(historyList.getByText(new RegExp(`#${id}`))).toBeVisible();
  await screenshot(page, 'registry-response-history');

  harness.expectedCancelledEvidenceIds.add(5183);
  await versionSelect.selectOption(`sha:${registryShaA}`);
  await expect(dialog.getByText('ЖК Учебный дом', { exact: true })).toBeVisible();
  await expect(dialog.getByText('ГАРАНТИЯ-ТЕСТ-001', { exact: true })).toBeVisible();
  await expect(dialog.getByText('ЖК Учебный дом · актуальные сведения', { exact: true })).toHaveCount(0);
  harness.expectedCancelledEvidenceIds.add(5182);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();

  await registryAction.click();
  const reopened = page.getByRole('dialog', { name: 'Сведения из реестра' });
  await expect(reopened.getByLabel('Сохранённые версии')).toHaveValue(`sha:${registryShaB}`);
  await expect(reopened.getByText('ЖК Учебный дом · актуальные сведения', { exact: true })).toBeVisible();
  await screenshot(page, 'registry-response-latest');
  await page.setViewportSize({ width: 320, height: 844 });
  const mobileDialogBox = await reopened.boundingBox();
  expect(mobileDialogBox).not.toBeNull();
  expect(mobileDialogBox!.x).toBeGreaterThanOrEqual(0);
  expect(mobileDialogBox!.x + mobileDialogBox!.width).toBeLessThanOrEqual(320);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await screenshot(page, 'registry-response-latest-320');
  await page.screenshot({ path: `${screenshotDir}/registry-response-latest-320-viewport.png` });
  const dialogHasScrollableContent = await page.evaluate(() => {
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    if (!dialog) return false;
    return [dialog, ...dialog.querySelectorAll<HTMLElement>('*')].some((element) => {
      const style = getComputedStyle(element);
      return element.scrollHeight > element.clientHeight + 1 && ['auto', 'scroll'].includes(style.overflowY);
    });
  });
  expect(dialogHasScrollableContent).toBe(true);
  await page.mouse.move(160, 720);
  await page.mouse.wheel(0, 600);
  await expect.poll(() => page.evaluate(() => {
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    if (!dialog) return false;
    return [dialog, ...dialog.querySelectorAll<HTMLElement>('*')].some((element) => element.scrollTop > 0);
  })).toBe(true);
  harness.expectedCancelledEvidenceIds.add(5183);
  await page.keyboard.press('Escape');
  await expect(reopened).toBeHidden();

  expect(harness.evidenceRequests.length).toBeGreaterThanOrEqual(3);
  expect(harness.evidenceRequests.every((request) => request.authorization === 'Bearer mock-ui-session')).toBe(true);
  expect(harness.mutations).toEqual([]);
  expectCleanBrowser(harness);
});

test('registry response reports unsupported and malformed archives and keeps the original download', async ({ page }) => {
  const object = makeRegistryObject();
  object.documents[0].evidence = [
    makeEvidence(5301, 'registry_response', 'application/json', 'e'.repeat(64), '2026-10-14T09:00:00Z'),
    makeEvidence(5302, 'registry_response', 'application/json', 'f'.repeat(64), '2026-10-16T11:00:00Z'),
  ];
  const harness = await installMocks(page, 'mio_officer', {
    object,
    evidenceContents: {
      5301: { contentType: 'application/json', body: '{not-json' },
      5302: { contentType: 'application/json', body: '{"success":true,"data":{"unrecognized":{}}}' },
    },
  });
  await page.goto('/objects/7');
  await page.getByRole('button', { name: 'Открыть сохранённые сведения из реестра' }).click();
  const dialog = page.getByRole('dialog', { name: 'Сведения из реестра' });
  await expect(dialog.getByText('Формат сохранённого ответа не распознан. Оригинал можно скачать.')).toBeVisible();
  await expect(dialog).not.toContainText('"success":true');

  const downloadPromise = page.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Скачать исходный ответ' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('registry-response-5302.json');
  await expect.poll(() => harness.evidenceRequests.some((request) => request.id === 5302)).toBe(true);

  harness.expectedCancelledEvidenceIds.add(5302);
  await dialog.getByLabel('Сохранённые версии').selectOption(`sha:${'e'.repeat(64)}`);
  await expect(dialog.getByText('Сохранённый ответ повреждён или не читается как JSON. Оригинал можно скачать.')).toBeVisible();
  expect(harness.evidenceRequests.filter((request) => request.id === 5301).length).toBeGreaterThanOrEqual(1);
  expect(harness.evidenceRequests.every((request) => request.authorization === 'Bearer mock-ui-session')).toBe(true);
  expect(harness.mutations).toEqual([]);
  harness.expectedCancelledEvidenceIds.add(5301);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  expectCleanBrowser(harness);
});

test('registry response load failure offers a working retry', async ({ page }) => {
  const object = makeRegistryObject();
  object.documents[0].evidence = [
    makeEvidence(5401, 'registry_response', 'application/json', '9'.repeat(64), '2026-10-16T11:00:00Z'),
  ];
  const harness = await installMocks(page, 'mio_officer', {
    object,
    evidenceContents: {
      5401: { contentType: 'application/json', body: registryResponseJson('ЖК Повторная проверка', 'ГАРАНТИЯ-ТЕСТ-003') },
    },
    evidenceFailures: { 5401: 4 },
  });
  await page.goto('/objects/7');
  await page.getByRole('button', { name: 'Открыть сохранённые сведения из реестра' }).click();
  const dialog = page.getByRole('dialog', { name: 'Сведения из реестра' });
  await expect(dialog.getByRole('alert')).toContainText('Не удалось загрузить сохранённый ответ. Повторите попытку или скачайте оригинал.');
  await dialog.getByRole('button', { name: 'Повторить загрузку' }).click();
  await expect(dialog.getByText('ЖК Повторная проверка', { exact: true })).toBeVisible();
  expect(harness.evidenceRequests.every((request) => request.authorization === 'Bearer mock-ui-session')).toBe(true);
  expect(harness.mutations).toEqual([]);
  harness.expectedCancelledEvidenceIds.add(5401);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
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

test.describe('Ask AI panel', () => {
  const panelName = 'Спросить ИИ';

  test('opens from the header with page starters, takes focus and returns it on Escape', async ({ page }) => {
    const harness = await installMocks(page, 'mio_officer');
    await page.goto('/objects/7');
    const opener = page.getByRole('button', { name: panelName });
    await opener.click();
    const panel = page.getByRole('complementary', { name: panelName });
    await expect(panel).toBeVisible();
    await expect(panel.getByRole('heading', { level: 2, name: /^(Доброе утро|Добрый день|Добрый вечер)\.$/ })).toBeVisible();
    await expect(panel.getByText('Чем займёмся?')).toBeVisible();
    await expect(panel.getByRole('button', { name: /Почему у объекта такая зона\?/ })).toBeVisible();
    await expect(panel.getByRole('button', { name: /Какие документы проверить\?/ })).toBeVisible();
    await expect(panel.getByText('Объект № 7')).toBeVisible();
    await expect(panel.getByText('ИИ может ошибаться. Проверяйте данные в карточках.')).toBeVisible();
    await expect(panel.getByRole('textbox', { name: 'Сообщение ассистенту' })).toBeFocused();
    await screenshot(page, 'assistant-empty-desktop');

    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(opener).toBeFocused();
    expectCleanBrowser(harness);
  });

  test('a starter sends the page entity and language; the markdown answer links navigate without reload', async ({ page }) => {
    const harness = await installMocks(page, 'mio_officer');
    await page.goto('/objects/7');
    await page.getByRole('button', { name: panelName }).click();
    const panel = page.getByRole('complementary', { name: panelName });
    await panel.getByRole('button', { name: /Почему у объекта такая зона\?/ }).click();

    await expect(panel.getByText('жёлтой', { exact: true })).toBeVisible();
    expect(harness.mutations.find((item) => item.path === '/assistant/chat')?.body).toEqual({
      messages: [{ role: 'user', content: 'Почему у объекта такая зона?' }],
      page: { path: '/objects/7', entity: { type: 'object', id: 7 } },
      language: 'ru',
    });
    await expect(panel.getByText('Ищу объекты: Северный')).toBeVisible();
    await expect(panel.getByRole('listitem').filter({ hasText: 'пункт два' })).toBeVisible();
    await expect(panel.getByRole('link', { name: 'документацию' })).toHaveCount(0);
    await expect(panel.getByText('документацию (example.invalid)')).toBeVisible();

    const sourcesToggle = panel.getByRole('button', { name: 'Источники (2)' });
    await expect(sourcesToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(panel.getByRole('link', { name: 'Зоны риска' })).toHaveCount(0);
    await sourcesToggle.click();
    await expect(panel.getByRole('link', { name: 'Зоны риска' })).toHaveAttribute('href', '/work');
    await expect(panel.getByText('Термины', { exact: true })).toBeVisible();
    await screenshot(page, 'assistant-answer-desktop');

    await page.goto('/work');
    await expect(panel).toBeVisible();
    await page.evaluate(() => { (window as unknown as { noReload: boolean }).noReload = true; });
    await panel.getByRole('link', { name: 'ЖК Северный бриз' }).click();
    await expect(page).toHaveURL(/\/objects\/7$/);
    expect(await page.evaluate(() => (window as unknown as { noReload?: boolean }).noReload)).toBe(true);
    expectCleanBrowser(harness);
  });

  test('keeps the conversation after reload, lists it and starts a new one', async ({ page }) => {
    await installMocks(page, 'mio_officer');
    await page.goto('/work');
    await page.getByRole('button', { name: panelName }).click();
    const panel = page.getByRole('complementary', { name: panelName });
    await panel.getByRole('button', { name: /С чего начать день\?/ }).click();
    await expect(panel.getByText('жёлтой', { exact: true })).toBeVisible();

    await page.reload();
    await expect(panel).toBeVisible();
    await expect(panel.getByText('жёлтой', { exact: true })).toBeVisible();
    await panel.getByRole('button', { name: 'Диалоги' }).click();
    await expect(page.getByRole('list', { name: 'Диалоги' }).getByRole('button', { name: 'С чего начать день?', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Новый диалог' }).first().click();
    await expect(panel.getByRole('button', { name: /С чего начать день\?/ })).toBeVisible();
    await expect(panel.getByText('жёлтой', { exact: true })).toHaveCount(0);

    await panel.getByRole('button', { name: 'Диалоги' }).click();
    await page.getByRole('button', { name: 'С чего начать день?', exact: true }).click();
    await expect(panel.getByText('жёлтой', { exact: true })).toBeVisible();
    await panel.getByRole('button', { name: 'Диалоги' }).click();
    await page.getByRole('button', { name: 'Удалить диалог: С чего начать день?' }).click();
    await expect(page.getByRole('button', { name: 'Удалить диалог: С чего начать день?' })).toHaveCount(0);
    await expect(panel.getByRole('heading', { level: 2 })).toBeVisible();
  });

  test('Enter sends, Shift+Enter adds a line, the page chip can be removed for one message', async ({ page }) => {
    const harness = await installMocks(page, 'mio_officer');
    await page.goto('/ads?ad=11');
    await page.getByRole('button', { name: panelName }).click();
    const panel = page.getByRole('complementary', { name: panelName });
    await expect(panel.getByText('Объявление № 11')).toBeVisible();
    await expect(panel.getByRole('button', { name: /Как подтвердить находки ИИ\?/ })).toBeVisible();
    const composer = panel.getByRole('textbox', { name: 'Сообщение ассистенту' });
    await composer.fill('первая');
    await composer.press('Shift+Enter');
    await composer.pressSequentially('вторая');
    expect(harness.mutations).toEqual([]);
    await panel.getByRole('button', { name: 'Не передавать страницу в этом сообщении' }).click();
    await composer.press('Enter');
    await expect(panel.getByText('жёлтой', { exact: true })).toBeVisible();
    expect(harness.mutations.find((item) => item.path === '/assistant/chat')?.body).toEqual({
      messages: [{ role: 'user', content: 'первая\nвторая' }],
      language: 'ru',
    });
    await expect(panel.getByText('Объявление № 11')).toBeVisible();
  });

  test('an error event shows inline and Retry asks again', async ({ page }) => {
    const failed = sse([{ type: 'delta', text: 'Начало' }, { type: 'error', code: 'llm_unavailable', message: 'down' }]);
    const harness = await installMocks(page, 'mio_officer', { assistantReplies: [failed] });
    await page.goto('/work');
    await page.getByRole('button', { name: panelName }).click();
    const panel = page.getByRole('complementary', { name: panelName });
    await panel.getByRole('button', { name: /С чего начать день\?/ }).click();
    await expect(panel.getByRole('alert')).toContainText('Языковая модель сейчас недоступна');
    await panel.getByRole('button', { name: 'Повторить' }).click();
    await expect(panel.getByText('жёлтой', { exact: true })).toBeVisible();
    await expect(panel.getByRole('alert')).toHaveCount(0);
    const chats = harness.mutations.filter((item) => item.path === '/assistant/chat');
    expect(chats).toHaveLength(2);
    expect(chats[1]?.body).toEqual(chats[0]?.body);
  });

  test('a stream that ends without done is shown as an error with Retry', async ({ page }) => {
    const cut = sse([{ type: 'delta', text: 'Начало' }]);
    const harness = await installMocks(page, 'mio_officer', { assistantReplies: [cut] });
    await page.goto('/work');
    await page.getByRole('button', { name: panelName }).click();
    const panel = page.getByRole('complementary', { name: panelName });
    await panel.getByRole('button', { name: /С чего начать день\?/ }).click();
    await expect(panel.getByRole('alert')).toContainText('Связь прервалась');
    await panel.getByRole('button', { name: 'Повторить' }).click();
    await expect(panel.getByText('жёлтой', { exact: true })).toBeVisible();
    await expect(panel.getByRole('alert')).toHaveCount(0);
    expect(harness.mutations.filter((item) => item.path === '/assistant/chat')).toHaveLength(2);
  });

  test('Stop aborts the stream and keeps the answer marked as stopped', async ({ page }) => {
    const harness = await installMocks(page, 'mio_officer', { assistantHangs: true });
    await page.goto('/signals');
    await page.getByRole('button', { name: panelName }).click();
    const panel = page.getByRole('complementary', { name: panelName });
    await panel.getByRole('button', { name: /Как отправить карточку в ГАСК\?/ }).click();
    await panel.getByRole('button', { name: 'Остановить' }).click();
    await expect(panel.getByText('Остановлено', { exact: true })).toBeVisible();
    await expect(panel.getByRole('button', { name: 'Отправить' })).toBeVisible();
    expect(harness.unexpected).toEqual([]);
    expect(harness.pageErrors).toEqual([]);
  });

  test('is absent when the module is off', async ({ page }) => {
    const harness = await installMocks(page, 'mio_officer', { assistantEnabled: false });
    await page.goto('/work');
    await expect(page.getByRole('group', { name: 'Действия и настройки' })).toBeVisible();
    await expect(page.getByRole('button', { name: panelName })).toHaveCount(0);
    await expect(page.getByRole('complementary', { name: panelName })).toHaveCount(0);
    expect(harness.unexpected).toEqual([]);
    expect(harness.pageErrors).toEqual([]);
  });

  test('covers the screen on a phone and closes back to the header button', async ({ page }) => {
    const harness = await installMocks(page, 'mio_officer');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/work');
    const opener = page.getByRole('button', { name: panelName });
    await opener.click();
    const panel = page.getByRole('complementary', { name: panelName });
    await expect(panel).toBeVisible();
    expect(await panel.boundingBox()).toMatchObject({ x: 0, y: 0, width: 390, height: 844 });
    await screenshot(page, 'assistant-empty-mobile');
    await panel.getByRole('button', { name: /С чего начать день\?/ }).click();
    await expect(panel.getByText('жёлтой', { exact: true })).toBeVisible();
    await screenshot(page, 'assistant-answer-mobile');
    await panel.getByRole('link', { name: 'ЖК Северный бриз' }).click();
    await expect(page).toHaveURL(/\/objects\/7$/);
    await expect(panel).toBeHidden();
    await opener.click();
    await panel.getByRole('button', { name: 'Закрыть' }).click();
    await expect(panel).toBeHidden();
    await expect(opener).toBeFocused();
    expectCleanBrowser(harness);
  });
});

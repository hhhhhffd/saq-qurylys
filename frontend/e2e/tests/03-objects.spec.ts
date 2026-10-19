import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { apiAs, findObject } from '../support/api';
import { OBJECT } from '../support/demo';
import { authFile } from '../support/users';
import { riskSummary } from '../support/ui';

test.use({ storageState: authFile('mio') });

test.describe('objects list', () => {
  test('searching by name finds the object with its score and zone', async ({ page }) => {
    await page.goto('/objects');
    await expect(page.getByRole('heading', { level: 1, name: t('objects:list.title') })).toBeVisible();

    await page.getByPlaceholder(t('objects:list.search')).fill('Северный бриз');

    const rows = page.getByRole('row').filter({ hasText: OBJECT.northBreeze });
    await expect(rows).toHaveCount(1);
    await expect(rows.getByRole('cell', { name: '35', exact: true })).toBeVisible();
    await expect(rows.getByRole('cell', { name: t('enums:zone.yellow'), exact: true })).toBeVisible();
    // Only the match is left in the table (the header row is not counted).
    await expect(page.getByRole('row')).toHaveCount(2);

    await rows.getByRole('link', { name: OBJECT.northBreeze }).click();
    await expect(page).toHaveURL(/\/objects\/\d+$/);
  });

  test('the zone filter narrows the table', async ({ page }) => {
    await page.goto('/objects');
    await page.getByLabel(t('objects:list.zoneFilter')).getByText(t('enums:zone.red'), { exact: true }).click();

    await expect(page).toHaveURL(/zone=red/);
    const rows = page.getByRole('row').filter({ has: page.getByRole('link') });
    await expect
      .poll(async () => {
        const texts = await rows.allInnerTexts();
        return texts.length > 0 && texts.every((text) => text.includes(t('enums:zone.red')));
      })
      .toBe(true);
  });
});

test.describe('object card «Золотая осень»', () => {
  let objectId: number;

  test.beforeAll(async () => {
    const api = await apiAs('mio');
    try {
      objectId = (await findObject(api, OBJECT.goldenAutumn)).id;
    } finally {
      await api.dispose();
    }
  });

  test.beforeEach(async ({ page }) => {
    await page.goto(`/objects/${objectId}`);
    await expect(page.getByRole('heading', { level: 1, name: OBJECT.goldenAutumn })).toBeVisible();
    await expect(riskSummary(page)).toBeVisible();
  });

  test('a deep link opens the requested tab and keeps the overview as the default', async ({ page }) => {
    await expect(page.getByRole('tab', { name: t('objects:card.tabs.overview') })).toHaveAttribute('aria-selected', 'true');

    await page.goto(`/objects/${objectId}?tab=complaints`);
    await expect(page.getByRole('tab', { name: new RegExp(`^${t('objects:card.tabs.complaints')}`) })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(page.getByRole('heading', { level: 3, name: t('objects:card.complaints.title') })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole('tab', { name: t('objects:card.tabs.overview') })).toHaveAttribute('aria-selected', 'true');
  });

  test('shows the score 70 and the red zone', async ({ page }) => {
    await expect(riskSummary(page)).toContainText('70');
    await expect(riskSummary(page)).toContainText(t('enums:zone.red'));
    await expect(page.getByText(t('objects:card.breakdown.total', { value: 70 }), { exact: true })).toBeVisible();
    await expect(page.getByText(t('enums:zone_reason.r1_and_r2'), { exact: true })).toBeVisible();
  });

  test('breaks the score down into R1, R2 and R3', async ({ page }) => {
    const factor = (label: string, code: string) =>
      page.getByRole('listitem').filter({ hasText: new RegExp(`^${label}\\s*${t(`enums:risk_factor.${code}`)}`) });
    const triggered = t('objects:card.breakdown.triggered');

    const r1 = factor('R1', 'r1_no_legal_basis');
    const r2 = factor('R2', 'r2_money_offer');
    const r3 = factor('R3', 'r3_active_ads');
    for (const [item, weight] of [
      [r1, '+35'],
      [r2, '+25'],
      [r3, '+10'],
    ] as const) {
      await expect(item).toContainText(triggered);
      await expect(item).toContainText(weight);
    }
    // R2 points at the phrase it found.
    await expect(r2).toContainText(/внесите депозит/i);

    for (const [label, code] of [
      ['R4', 'r4_collective_complaint'],
      ['R5', 'r5_readiness_mismatch'],
      ['R6', 'r6_stalled_or_delayed'],
    ]) {
      const item = factor(label, code);
      await expect(item).toContainText(t('objects:card.breakdown.notTriggered'));
      await expect(item).not.toContainText(triggered);
    }
  });

  test('shows the legal basis as absent, with the check of each document', async ({ page }) => {
    const block = page.getByRole('region', { name: t('objects:card.legalBasis.title') });
    await expect(block).toBeVisible();
    await expect(block).toContainText(t('enums:legal_basis_status.absent_established'));
    await expect(block).toContainText(t('objects:card.legalBasis.hint.absent_established'));
    for (const doc of ['guarantee', 'dsu_permit']) {
      await expect(block.getByText(t(`enums:doc_type.${doc}`), { exact: true })).toBeVisible();
    }
    await expect(block.getByText(t('enums:check_status.not_found'))).toHaveCount(2);
  });

  test('lists the documents with the result of the registry check', async ({ page }) => {
    await page.getByRole('tab', { name: new RegExp(`^${t('objects:card.tabs.documents')}`) }).click();
    await expect(page).toHaveURL(/[?&]tab=documents/);
    await expect(page.getByRole('heading', { level: 3, name: t('objects:card.documents.title') })).toBeVisible();

    for (const doc of ['guarantee', 'dsu_permit']) {
      const row = page.getByRole('row').filter({ hasText: t(`enums:doc_type.${doc}`) });
      await expect(row).toBeVisible();
      await expect(row).toContainText(t('enums:check_status.not_found'));
    }
    // Documents nobody entered are listed as missing, not as violations.
    await expect(page.getByRole('heading', { level: 4, name: t('objects:card.documents.missingTitle') })).toBeVisible();
  });

  test('links to the publications of the object', async ({ page }) => {
    const link = page.getByRole('link', { name: /публикац/ }).filter({ hasNotText: /#/ });
    await expect(link).toHaveAttribute('href', /\/ads\?object_id=\d+/);
    await link.click();

    await expect(page).toHaveURL(/\/ads\?object_id=\d+/);
    const ads = page.getByRole('article');
    await expect
      .poll(async () => {
        const texts = await ads.allInnerTexts();
        return texts.length > 0 && texts.every((text) => text.includes(OBJECT.goldenAutumn));
      })
      .toBe(true);
  });

  test('opens the link graph of the object', async ({ page }) => {
    await page.getByRole('tab', { name: t('objects:card.tabs.history') }).click();
    await page.getByRole('link', { name: t('graph:open') }).click();

    await expect(page).toHaveURL(new RegExp(`/graph\\?object_id=${objectId}$`));
    await expect(page.getByRole('heading', { level: 1, name: t('graph:title') })).toBeVisible();
    await expect(page.getByText(t('graph:focus.object', { name: OBJECT.goldenAutumn }))).toBeVisible();
  });
});

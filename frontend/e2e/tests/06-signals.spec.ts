import { readFile } from 'node:fs/promises';
import type { Page } from '@playwright/test';
import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { OBJECT } from '../support/demo';
import { authFile } from '../support/users';

test.use({ storageState: authFile('mio') });

/** The card the system drafted when «Золотая осень» turned red; the specs only read it. */
async function openAutoCard(page: Page): Promise<string> {
  await page.goto('/signals');
  await expect(page.getByRole('heading', { level: 1, name: t('nav.signals') })).toBeVisible();
  const row = page.getByRole('row').filter({ hasText: OBJECT.goldenAutumn });
  await expect(row).toHaveCount(1);
  const number = row.getByRole('link', { name: /^SQ-\d{4}-\d{4}$/ });
  await expect(number).toBeVisible();
  const text = await number.innerText();
  await number.click();
  await expect(page).toHaveURL(/\/signals\/\d+$/);
  await expect(page.getByRole('heading', { level: 1, name: text })).toBeVisible();
  return text;
}

test('the list shows the automatic card of «Золотая осень»', async ({ page }) => {
  await page.goto('/signals');
  const row = page.getByRole('row').filter({ hasText: OBJECT.goldenAutumn });
  await expect(row).toHaveCount(1);
  await expect(row.getByRole('link', { name: /^SQ-\d{4}-\d{4}$/ })).toBeVisible();
  await expect(row).toContainText(t('enums:zone.red'));
  await expect(page.getByRole('button', { name: t('signals:list.create') })).toBeVisible();
});

test('the card has all its sections and the decisions of the officer', async ({ page }) => {
  await openAutoCard(page);

  await expect(page.getByRole('heading', { level: 1, name: /^SQ-\d{4}-\d{4}$/ })).toBeVisible();
  // The audit journal below repeats the origin and the status when it lists the changes, hence the first match.
  await expect(page.getByText(t('enums:origin.auto'), { exact: true }).first()).toBeVisible();
  await expect(page.getByText(t('enums:signal_status.requires_confirmation'), { exact: true }).first()).toBeVisible();

  for (const section of [
    'object_developer',
    'risk_factors',
    'permit_checks',
    'publications',
    'scheme_payments',
    'proposed_measures',
    'route',
    'note',
  ]) {
    await expect(page.getByRole('heading', { level: 3, name: t(`signals:sections.${section}`) })).toBeVisible();
  }
  await expect(page.getByRole('heading', { level: 3, name: t('signals:audit.title') })).toBeVisible();

  // The two decisions are there; the card is not touched (no recipient yet, so sending is not even possible).
  await expect(page.getByRole('button', { name: t('signals:actions.return') })).toBeEnabled();
  await expect(page.getByRole('button', { name: t('signals:actions.confirmSend') })).toBeVisible();
  await expect(page.getByRole('button', { name: t('signals:actions.confirmSend') })).toBeDisabled();
});

test('the PDF of the card downloads as application/pdf', async ({ page }) => {
  const number = await openAutoCard(page);

  const [response, download] = await Promise.all([
    page.waitForResponse((r) => /\/api\/v1\/signals\/\d+\/pdf$/.test(new URL(r.url()).pathname)),
    page.waitForEvent('download'),
    page.getByRole('button', { name: t('signals:detail.pdf') }).click(),
  ]);

  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/pdf');
  // What the browser saved is a PDF file.
  expect((await readFile(await download.path())).subarray(0, 4).toString()).toBe('%PDF');
  expect(download.suggestedFilename()).toBe(`${number}.pdf`);
});

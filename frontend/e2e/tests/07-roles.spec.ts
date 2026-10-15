import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { ADMIN_PASSWORD } from '../support/env';
import { authFile } from '../support/users';

const REGISTRY_PAGES = ['/map', '/objects', '/ads', '/graph', '/sources', '/admin'];

for (const [role, label] of [
  ['gask', 'ГАСК'],
  ['police', 'правоохранительные органы'],
] as const) {
  test.describe(`recipient: ${label}`, () => {
    test.use({ storageState: authFile(role) });

    test('sees only the signals section and is sent back from the registry pages', async ({ page }) => {
      await page.goto('/');
      await expect(page).toHaveURL(/\/signals$/);

      const nav = page.getByRole('navigation', { name: t('header.menu') });
      await expect(nav.getByRole('link', { name: t('nav.signals') })).toBeVisible();
      for (const hidden of ['map', 'objects', 'ads', 'graph', 'admin']) {
        await expect(nav.getByRole('link', { name: t(`nav.${hidden}`) })).toHaveCount(0);
      }
      await expect(page.getByText(t('activity:idle'), { exact: true })).toHaveCount(0);

      for (const path of REGISTRY_PAGES) {
        await page.goto(path);
        await expect(page).toHaveURL(/\/signals$/);
        await expect(page.getByRole('heading', { level: 1, name: t('nav.signals') })).toBeVisible();
      }
      // A recipient sees only the cards sent to the body, so there is no way to start a card.
      await expect(page.getByRole('button', { name: t('signals:list.create') })).toHaveCount(0);
    });
  });
}

test.describe('registry officer', () => {
  test.use({ storageState: authFile('mio') });

  test('has the registry sections but not the administration', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/map$/);

    const nav = page.getByRole('navigation', { name: t('header.menu') });
    for (const shown of ['map', 'objects', 'ads', 'graph', 'signals']) {
      await expect(nav.getByRole('link', { name: t(`nav.${shown}`) })).toBeVisible();
    }
    await expect(nav.getByRole('link', { name: t('nav.admin') })).toHaveCount(0);

    await page.goto('/admin');
    await expect(page).toHaveURL(/\/map$/);
  });
});

test.describe('administrator', () => {
  test.skip(!ADMIN_PASSWORD, 'SAQ_ADMIN_PASSWORD is not set (e2e/run.sh reads it from .env)');
  test.use({ storageState: authFile('admin') });

  test('sees the administration sections', async ({ page }) => {
    await page.goto('/');
    const nav = page.getByRole('navigation', { name: t('header.menu') });
    await expect(nav.getByRole('link', { name: t('nav.admin') })).toBeVisible();
    await nav.getByRole('link', { name: t('nav.admin') }).click();

    await expect(page).toHaveURL(/\/admin\/users$/);
    await expect(page.getByRole('heading', { level: 1, name: t('admin:title') })).toBeVisible();
    const sections = page.getByRole('navigation', { name: t('admin:sectionsLabel') });
    for (const section of ['users', 'factors', 'phrases', 'holidays', 'settings', 'territories', 'registry']) {
      await expect(sections.getByRole('link', { name: t(`admin:sections.${section}`), exact: true })).toBeVisible();
    }
    // The user list holds the demo accounts.
    await expect(page.getByRole('heading', { level: 2, name: t('admin:users.title') })).toBeVisible();
    for (const username of ['admin', 'demo_mio', 'demo_gask', 'demo_police']) {
      await expect(page.getByRole('cell', { name: username, exact: true })).toBeVisible();
    }
  });

  test('the factor weights and the phrase dictionary load', async ({ page }) => {
    await page.goto('/admin/factors');
    await expect(page.getByRole('heading', { level: 2, name: t('admin:factors.title') })).toBeVisible();
    for (const factor of ['r1_no_legal_basis', 'r2_money_offer', 'r3_active_ads']) {
      await expect(page.getByRole('row').filter({ hasText: t(`enums:risk_factor.${factor}`) })).toBeVisible();
    }

    await page.goto('/admin/phrases');
    await expect(page.getByRole('heading', { level: 2, name: t('admin:phrases.title') })).toBeVisible();
    await expect(page.getByRole('row').filter({ hasText: 'бронирование' }).first()).toBeVisible();
  });

  test('the settings page loads and nothing is edited', async ({ page }) => {
    await page.goto('/admin/settings');
    await expect(page.getByRole('heading', { level: 2, name: t('admin:settings.title') })).toBeVisible();

    const reviewDays = page.getByRole('textbox', { name: t('enums:setting.review_days'), exact: true });
    await expect(reviewDays).toHaveValue(/^\d+$/);
    await expect(page.getByRole('heading', { level: 3, name: t('admin:settings.groups.zones') })).toBeVisible();
    // Nothing was changed, so there is nothing to save.
    await expect(page.getByRole('button', { name: t('save') })).toBeDisabled();
  });
});

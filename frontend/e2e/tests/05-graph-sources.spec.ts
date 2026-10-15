import { expect, test } from '../support/test';
import { t, numberedPattern } from '../support/i18n';
import { authFile } from '../support/users';

test.use({ storageState: authFile('mio') });

test.describe('link graph', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/graph');
    await expect(page.getByRole('heading', { level: 1, name: t('graph:title') })).toBeVisible();
  });

  test('the findings panel names the phone shared by three developers; selecting it keeps the graph alive', async ({
    page,
  }) => {
    const canvas = page
      .getByRole('group', { name: numberedPattern('graph:canvas.label', ['nodes', 'edges']) })
      .locator('canvas');
    await expect(canvas.first()).toBeVisible();

    const finding = page.getByRole('button', { name: t('graph:findings.shared_phone_few', { count: 3 }) });
    await expect(page.getByRole('heading', { level: 3, name: t('graph:findings.title') })).toBeVisible();
    await expect(finding).toBeVisible();
    await expect(finding).toContainText(t('graph:findings.objects_few', { count: 3 }));

    await finding.click();

    await expect(finding).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: t('graph:findings.clear') })).toBeVisible();
    await expect(canvas.first()).toBeVisible();
    await expect(page.getByRole('heading', { level: 1, name: t('graph:title') })).toBeVisible();

    await page.getByRole('button', { name: t('graph:findings.clear') }).click();
    await expect(finding).toHaveAttribute('aria-pressed', 'false');
  });

  test('lists the candidate source «prime_estate_demo» without accepting or dismissing it', async ({ page }) => {
    await expect(page.getByRole('heading', { level: 3, name: t('graph:suggestions.title') })).toBeVisible();
    await expect(
      page.getByRole('link', { name: t('graph:suggestions.openProfile', { handle: 'prime_estate_demo' }) }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: t('graph:suggestions.accept') })).toBeVisible();
    await expect(page.getByRole('button', { name: t('graph:suggestions.dismiss') })).toBeVisible();
  });
});

test('sources: the page shows every collector as switched off', async ({ page }) => {
  await page.goto('/sources');
  await expect(page.getByRole('heading', { level: 1, name: t('sources:title') })).toBeVisible();
  await expect(page.getByRole('heading', { level: 3, name: t('sources:collectors.title') })).toBeVisible();

  for (const collector of ['instagram', 'telegram', 'olx', 'krisha']) {
    const badge = page.getByRole('listitem').filter({ hasText: t(`sources:collectors.names.${collector}`) });
    await expect(badge).toHaveCount(1);
    await expect(badge).toContainText(t('sources:collectors.off'));
    await expect(badge).not.toContainText(t('sources:collectors.on'));
  }
});

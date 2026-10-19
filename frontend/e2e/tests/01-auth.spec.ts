import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { CREDENTIALS } from '../support/users';

test.describe('signed out', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('a protected page sends an anonymous visitor to the login form', async ({ page }) => {
    await page.goto('/objects');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('heading', { name: t('auth.title') })).toBeVisible();
  });

  test('a wrong password shows an error and keeps the login form', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(t('auth.username'), { exact: true }).fill(CREDENTIALS.mio.username);
    await page.getByLabel(t('auth.password'), { exact: true }).fill('wrong-password-e2e');
    await page.getByRole('button', { name: t('auth.login') }).click();

    await expect(page.getByRole('alert')).toHaveText(t('auth.invalidCredentials'));
    await expect(page).toHaveURL(/\/login$/);
  });

  test('a registry officer signs in and lands on the tasks', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(t('auth.username'), { exact: true }).fill(CREDENTIALS.mio.username);
    await page.getByLabel(t('auth.password'), { exact: true }).fill(CREDENTIALS.mio.password ?? '');
    await page.getByRole('button', { name: t('auth.login') }).click();

    await expect(page).toHaveURL(/\/work$/);
    await expect(page.getByRole('heading', { level: 1, name: t('work.title') })).toBeVisible();
  });

  test('a recipient signs in and lands on the signals', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(t('auth.username'), { exact: true }).fill(CREDENTIALS.gask.username);
    await page.getByLabel(t('auth.password'), { exact: true }).fill(CREDENTIALS.gask.password ?? '');
    await page.getByRole('button', { name: t('auth.login') }).click();

    await expect(page).toHaveURL(/\/signals$/);
  });
});

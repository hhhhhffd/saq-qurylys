import { expect, test as setup } from './support/test';
import { t } from './support/i18n';
import { authFile, CREDENTIALS, type Role } from './support/users';

/** Signs in through the real login form once per role; the specs reuse the saved session. */
const ROLES: Role[] = ['mio', 'gask', 'police', 'admin'];

for (const role of ROLES) {
  setup(`sign in as ${role}`, async ({ page }) => {
    const { username, password } = CREDENTIALS[role];
    setup.skip(!password, 'SAQ_ADMIN_PASSWORD is not set (e2e/run.sh reads it from .env)');

    await page.goto('/login');
    // The suite asserts Russian wording whatever the account's own language is.
    await page.evaluate(() => localStorage.setItem('saq_lang', 'ru'));
    await page.getByLabel(t('auth.username'), { exact: true }).fill(username);
    await page.getByLabel(t('auth.password'), { exact: true }).fill(password ?? '');
    await page.getByRole('button', { name: t('auth.login') }).click();

    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('button', { name: t('header.userMenu') })).toBeVisible();
    await page.context().storageState({ path: authFile(role) });
  });
}

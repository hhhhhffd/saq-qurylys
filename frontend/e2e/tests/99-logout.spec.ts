import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { authFile } from '../support/users';

// Logout revokes every token of the user (token_version), including the saved session the other specs share,
// so this spec runs last.
test.describe('signed in', () => {
  test.use({ storageState: authFile('mio') });

  test('logout returns to the login form and drops the session', async ({ page }) => {
    await page.goto('/map');
    await page.getByRole('button', { name: t('header.userMenu') }).click();
    await page.getByRole('menuitem', { name: t('auth.logout') }).click();

    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('heading', { name: t('auth.title') })).toBeVisible();

    await page.goto('/map');
    await expect(page).toHaveURL(/\/login$/);
  });
});

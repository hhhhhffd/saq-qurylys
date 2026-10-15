import { expect, test } from '../support/test';
import { t, tKk } from '../support/i18n';
import { apiAs } from '../support/api';
import { authFile } from '../support/users';

test.use({ storageState: authFile('mio') });

const NAV = ['map', 'objects', 'ads', 'graph', 'signals'] as const;

test('the activity island idles as «Мониторинг» for a registry officer', async ({ page }) => {
  await page.goto('/map');
  await expect(page.getByText(t('activity:idle'), { exact: true })).toBeVisible();
  // Its live region is empty until an event is announced.
  await expect(page.getByTestId('activity-live-region')).toBeAttached();
});

test('the language switch changes the navigation to Kazakh and back', async ({ page }) => {
  await page.goto('/map');
  const nav = page.getByRole('navigation', { name: t('header.menu') });
  await expect(nav.getByRole('link', { name: t('nav.objects') })).toBeVisible();

  await page.getByText('ҚАЗ', { exact: true }).click();

  const kazakhNav = page.getByRole('navigation', { name: tKk('header.menu') });
  for (const item of NAV) await expect(kazakhNav.getByRole('link', { name: tKk(`nav.${item}`), exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: tKk('map:title') })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'kk');
  expect(await page.evaluate(() => localStorage.getItem('saq_lang'))).toBe('kk');

  await page.getByText('RU', { exact: true }).click();

  for (const item of NAV) await expect(nav.getByRole('link', { name: t(`nav.${item}`), exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: t('map:title') })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'ru');
  expect(await page.evaluate(() => localStorage.getItem('saq_lang'))).toBe('ru');
});

test('the notification bell opens and lists the unread notifications', async ({ page }) => {
  const api = await apiAs('mio');
  const unread = await api
    .get<{ items: unknown[] }>('/notifications?unread=true')
    .finally(() => api.dispose());

  await page.goto('/map');
  await page.getByRole('button', { name: t('header.notifications') }).click();

  const popup = page.getByRole('dialog');
  await expect(popup.getByText(t('header.notifications'), { exact: true })).toBeVisible();
  if (unread.items.length === 0) {
    await expect(popup.getByText(t('header.noNotifications'))).toBeVisible();
  } else {
    await expect(popup.getByRole('button', { name: t('header.markAllRead') })).toBeVisible();
    await expect(popup.getByRole('listitem')).toHaveCount(unread.items.length);
    // The demo database drafted a card for every red object, so someone has always been told about it.
    await expect(popup.getByRole('listitem').first()).toContainText(/\d{2}\.\d{2}\.\d{4}/);
  }
});

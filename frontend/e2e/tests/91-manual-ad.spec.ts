import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { apiAs, findObject } from '../support/api';
import { OBJECT } from '../support/demo';
import { authFile } from '../support/users';
import { choose, expectObjectScore } from '../support/ui';

test.use({ storageState: authFile('mio') });

// Not undone: the publication, the rescored object and the events stay in the demo database (see e2e/README.md).
test('a manually entered publication is highlighted, rescored and announced by the island', async ({ page }) => {
  test.setTimeout(150_000);
  const api = await apiAs('mio');
  const object = await findObject(api, OBJECT.birchGrove).finally(() => api.dispose());
  const scoreBefore = object.score ?? 0;

  const stamp = `E2E ${Date.now()}`;
  const text = `${stamp} Старт продаж! Забронируйте квартиру, первоначальный взнос 10 %`;

  // The island takes its starting point from the first poll of the feed; events after it are announced.
  const firstPoll = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/v1/activity');
  await page.goto('/ads');
  await expect(page.getByText(t('activity:idle'), { exact: true })).toBeVisible();
  await firstPoll;

  await page.getByRole('button', { name: t('ads:actions.manual') }).click();
  const dialog = page.getByRole('dialog', { name: t('ads:manual.title') });
  await dialog.getByRole('textbox', { name: t('ads:manual.text') }).fill(text);
  await choose(
    page,
    dialog.getByRole('combobox', { name: t('ads:manual.object'), exact: true }),
    new RegExp(OBJECT.birchGrove),
    'Берёзовая',
  );
  await dialog.getByRole('button', { name: t('ads:manual.submit'), exact: true }).click();

  // The new publication is opened above the feed, its phrases already marked.
  const pinned = page.getByRole('region', { name: t('ads:feed.pinned') });
  await expect(pinned).toContainText(stamp);
  const marks = pinned.getByTestId('phrase-mark');
  await expect(marks.filter({ hasText: /забронируйте/i })).toBeVisible();
  await expect(marks.filter({ hasText: /первоначальный взнос/i })).toBeVisible();

  // The island announces it within a few polls (every 4 s), through its live region.
  await expect(page.getByTestId('activity-live-region')).toContainText(OBJECT.birchGrove, { timeout: 25_000 });

  // It is in the feed too (found by its unique text), with the phrases marked.
  await page.goto('/ads');
  await page.getByPlaceholder(t('ads:filters.searchPlaceholder')).fill(stamp);
  const card = page.getByRole('article').filter({ hasText: stamp });
  await expect(card).toHaveCount(1);
  await expect(card).toContainText(OBJECT.birchGrove);
  await expect(card.getByTestId('phrase-mark').filter({ hasText: /забронируйте/i })).toBeVisible();

  // R2 and R3 arrive: 0 → 35 on the first run, never below 35 on the next ones.
  await expectObjectScore(page, object.id, (score) => score >= 35);
  if (scoreBefore === 0) {
    await expectObjectScore(page, object.id, 35);
  }
});

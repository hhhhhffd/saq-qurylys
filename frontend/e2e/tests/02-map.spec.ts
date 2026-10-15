import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { OBJECT } from '../support/demo';
import { authFile } from '../support/users';
import { mapObjectRows, readCounters, scoreOfRow, zoneButton, zoneCounters, ZONES } from '../support/ui';

test.use({ storageState: authFile('mio') });

test.beforeEach(async ({ page }) => {
  await page.goto('/map');
  await expect(page.getByRole('heading', { level: 1, name: t('map:title') })).toBeVisible();
  await expect(zoneCounters(page)).toBeVisible();
});

test('the zone counters show numbers that add up', async ({ page }) => {
  const counts = await readCounters(page);

  for (const zone of ZONES) expect(Number.isInteger(counts[zone])).toBe(true);
  expect(counts.total).toBeGreaterThan(0);
  expect(counts.green + counts.yellow + counts.red).toBeLessThanOrEqual(counts.total);
  // The demo database has objects of every zone.
  for (const zone of ZONES) expect(counts[zone]).toBeGreaterThan(0);
});

test('the map and the object list are shown, the list is sorted by score', async ({ page }) => {
  await expect(page.getByRole('region', { name: t('map:map.label') })).toBeVisible();

  const rows = mapObjectRows(page);
  await expect(rows.first()).toBeVisible();
  const scores = (await rows.allInnerTexts()).map(scoreOfRow);

  expect(scores.length).toBeGreaterThan(1);
  expect(scores).toEqual([...scores].sort((a, b) => b - a));
});

test('filtering by the red zone leaves red objects and opens the card of an object', async ({ page }) => {
  const counts = await readCounters(page);
  const red = zoneButton(page, 'red');
  await red.click();
  await expect(red).toHaveAttribute('aria-pressed', 'true');

  const rows = mapObjectRows(page);
  await expect(rows).toHaveCount(counts.red);
  for (const text of await rows.allInnerTexts()) expect(text).toContain(t('enums:zone.red'));

  const goldenAutumn = rows.filter({ hasText: OBJECT.goldenAutumn });
  await expect(goldenAutumn).toBeVisible();
  await goldenAutumn.click();

  await expect(page).toHaveURL(/\/objects\/\d+$/);
  await expect(page.getByRole('heading', { level: 1, name: OBJECT.goldenAutumn })).toBeVisible();
});

test('time machine: the slider moves the counters back and closing returns the live ones', async ({ page }) => {
  const live = await readCounters(page);
  const toggle = page.getByRole('button', { name: t('map:timeMachine.toggle') });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');

  const bar = page.getByRole('group', { name: t('map:timeMachine.bar') });
  const slider = bar.getByRole('slider', { name: t('map:timeMachine.slider') });
  const date = page.getByTestId('time-machine-date');
  await expect(slider).toBeVisible();
  await expect(date).toBeVisible();
  // The last frame is today and shows the live data.
  await expect(date).toContainText(t('map:timeMachine.today'));
  expect(await readCounters(page)).toEqual(live);

  const today = await date.innerText();
  await slider.focus();
  await page.keyboard.press('Home');

  await expect(date).not.toHaveText(today);
  await expect(date).not.toContainText(t('map:timeMachine.today'));
  // Half a year ago the objects were not red yet.
  await expect.poll(async () => (await readCounters(page)).red).toBeLessThan(live.red);
  expect((await readCounters(page)).total).toBe(live.total);

  await bar.getByRole('button', { name: t('map:timeMachine.close') }).click();
  await expect(bar).toHaveCount(0);
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => readCounters(page)).toEqual(live);
});

test('the reset button clears the zone filter', async ({ page }) => {
  await zoneButton(page, 'red').click();
  await page.getByRole('button', { name: t('reset') }).click();
  await expect(zoneButton(page, 'red')).toHaveAttribute('aria-pressed', 'false');
  await expect(mapObjectRows(page)).toHaveCount((await readCounters(page)).total);
});


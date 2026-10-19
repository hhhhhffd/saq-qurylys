import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { apiAs, findObject } from '../support/api';
import { OBJECT } from '../support/demo';
import { authFile } from '../support/users';
import { choose } from '../support/ui';

test.use({ storageState: authFile('mio') });

const articles = (page: import('@playwright/test').Page) => page.getByRole('article');
// The master list: one compact row per publication; the open one is the only article.
const rows = (page: import('@playwright/test').Page) =>
  page.getByRole('list', { name: t('ads:list.title') }).getByRole('listitem');

test('the feed renders publications with their phrases and a pager', async ({ page }) => {
  await page.goto('/ads');
  await expect(page.getByRole('heading', { level: 1, name: t('ads:title') })).toBeVisible();

  await expect(rows(page).first()).toBeVisible();
  expect(await rows(page).count()).toBeGreaterThan(1);
  // The first publication is open beside the list; the feed starts with the heaviest phrases.
  await expect(articles(page)).toHaveCount(1);
  await expect(articles(page).first().getByTestId('phrase-mark').first()).toBeVisible();
  await expect(page.getByRole('navigation', { name: t('ads:feed.pagination') })).toBeVisible();
  await expect(page.getByRole('button', { name: t('ads:actions.manual') })).toBeVisible();
});

test('opening the «Золотая осень» publication from the score shows the highlighted phrase', async ({ page }) => {
  const api = await apiAs('mio');
  const { id } = await findObject(api, OBJECT.goldenAutumn).finally(() => api.dispose());
  await page.goto(`/objects/${id}`);

  // R2 «Предложение внести деньги» names the publication that carries the phrase.
  const r2 = page
    .getByRole('listitem')
    .filter({ hasText: new RegExp(`^R2\\s*${t('enums:risk_factor.r2_money_offer')}`) });
  await r2.getByRole('link', { name: /#\d+/ }).click();

  await expect(page).toHaveURL(/\/ads\?ad=\d+&hit=\d+/);
  const pinned = page.getByRole('region', { name: t('ads:feed.pinned') });
  const card = pinned.getByRole('article');
  await expect(card).toContainText(OBJECT.goldenAutumn);
  await expect(card.getByTestId('phrase-mark').filter({ hasText: /внесите депозит/i })).toBeVisible();
  // The same phrase is listed with its category and where it comes from: the dictionary, or the officer's
  // confirmation once the mutation spec has run (it leaves the phrase confirmed).
  const phrase = card
    .getByRole('list', { name: t('ads:hits.title') })
    .getByRole('listitem')
    .filter({ hasText: /внесите депозит/i });
  await expect(phrase).toContainText(t('enums:phrase_category.deposit'));
  await expect(phrase).toContainText(new RegExp(`${t('enums:hit_source.dictionary')}|${t('enums:hit_source.confirmed')}`));
});

test('a removed publication shows its history with the time it stayed online', async ({ page }) => {
  await page.goto('/ads');
  await page.getByPlaceholder(t('ads:filters.searchPlaceholder')).fill('Малахит');

  const card = articles(page).filter({ hasText: OBJECT.malachite });
  await expect(card).toHaveCount(1);
  // The history sits in a collapsed block of the card.
  await card.getByText(t('ads:versions.details'), { exact: true }).click();
  const history = card.getByRole('region', { name: t('ads:versions.title') });
  await expect(history).toBeVisible();

  const duration = `2 ${t('ads:versions.units.h')} 15 ${t('ads:versions.units.min')}`;
  await expect(history).toContainText(t('ads:versions.removedAfter', { duration }));
  await expect(history).toContainText(t('ads:versions.captured'));
  await expect(history).toContainText(t('ads:versions.removed'));
  // The original and the later text side by side, with the changes marked.
  await expect(history.getByRole('heading', { name: t('ads:versions.compare') })).toBeVisible();
  await expect(history.getByText(t('ads:versions.legend'))).toBeVisible();
});

test('the platform filter narrows the feed and can be reset', async ({ page }) => {
  const telegram = t('enums:platform.telegram');
  // Content, not counts: both pages are capped by the page size, and the runs keep adding publications.
  const isTelegram = (text: string) => text.includes(telegram);
  await page.goto('/ads');
  await expect(rows(page).first()).toBeVisible();
  const all = await rows(page).count();
  expect((await rows(page).allInnerTexts()).some((text) => !isTelegram(text))).toBe(true);

  await choose(page, page.getByRole('combobox', { name: t('ads:filters.platform'), exact: true }), telegram);

  await expect(page).toHaveURL(/platform=telegram/);
  await expect
    .poll(async () => {
      const texts = await rows(page).allInnerTexts();
      return texts.length > 0 && texts.every(isTelegram);
    })
    .toBe(true);

  await page.getByRole('button', { name: t('reset') }).click();
  await expect(page).not.toHaveURL(/platform=/);
  await expect.poll(() => rows(page).count()).toBe(all);
  await expect.poll(async () => (await rows(page).allInnerTexts()).some((text) => !isTelegram(text))).toBe(true);
});

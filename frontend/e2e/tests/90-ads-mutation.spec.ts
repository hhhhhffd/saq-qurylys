import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { apiAs, findObject, objectScore, type Api } from '../support/api';
import { OBJECT } from '../support/demo';
import { authFile } from '../support/users';
import { expectObjectScore, riskSummary } from '../support/ui';

test.use({ storageState: authFile('mio') });

const DICTIONARY_PHRASE = /внесите депозит/i;

interface AdHit {
  id: number;
  matched_text: string;
  detected_by: string;
  confirmed: boolean | null;
}

/**
 * Puts the phrase back the way the scenario leaves it (confirmed) and waits for the score to follow, whatever
 * state a failed run left behind. The API has no way to return a hit to «not decided yet», so confirmed is the
 * resting state after the first run.
 */
async function restorePhrase(api: Api, objectId: number): Promise<void> {
  const ads = await api.get<{ items: { id: number }[] }>(`/ads?object_id=${objectId}&limit=50`);
  for (const { id: adId } of ads.items) {
    const detail = await api.get<{ phrase_hits: AdHit[] }>(`/ads/${adId}`);
    for (const hit of detail.phrase_hits) {
      if (hit.detected_by === 'dictionary' && DICTIONARY_PHRASE.test(hit.matched_text) && hit.confirmed === false) {
        await api.post(`/ads/${adId}/hits/${hit.id}/confirm`, { confirmed: true });
      }
    }
  }
  await expect
    .poll(() => objectScore(api, objectId), { message: 'the score of «Золотая осень» is back to 70', timeout: 60_000 })
    .toBe(70);
}

test('rejecting the dictionary phrase takes R2 off the score (70 → 45) and confirming it brings it back', async ({
  page,
}) => {
  const api = await apiAs('mio');
  const { id: objectId } = await findObject(api, OBJECT.goldenAutumn);
  try {
    await expectObjectScore(page, objectId, 70);

    // From the R2 line of the score to the publication with the phrase.
    const r2 = page
      .getByRole('listitem')
      .filter({ hasText: new RegExp(`^R2\\s*${t('enums:risk_factor.r2_money_offer')}`) });
    await r2.getByRole('link', { name: /#\d+/ }).click();
    await expect(page).toHaveURL(/\/ads\?ad=\d+&hit=\d+/);
    const adUrl = page.url();
    const hitId = new URL(adUrl).searchParams.get('hit');

    const phrase = () =>
      page
        .getByRole('region', { name: t('ads:feed.pinned') })
        .getByRole('list', { name: t('ads:hits.title') })
        .getByRole('listitem')
        .filter({ hasText: DICTIONARY_PHRASE });
    const decision = (confirmed: boolean) =>
      page.waitForResponse(
        (r) => r.request().method() === 'POST' && r.url().endsWith(`/hits/${hitId}/confirm`) && r.ok(),
      ).then((r) => expect(r.request().postDataJSON()).toEqual({ confirmed }));

    // Reject: the phrase is struck off, R2 no longer counts and the object leaves the red zone.
    await expect(phrase()).toBeVisible();
    await Promise.all([decision(false), phrase().getByRole('button', { name: t('ads:hits.reject') }).click()]);
    await expect(phrase()).toContainText(t('enums:hit_source.rejected'));
    await expectObjectScore(page, objectId, 45);
    await expect(riskSummary(page)).toContainText(t('enums:zone.yellow'));
    await expect(page.getByText(t('objects:card.breakdown.total', { value: 45 }), { exact: true })).toBeVisible();

    // Confirm it again: R2 is back.
    await page.goto(adUrl);
    await expect(phrase()).toContainText(t('enums:hit_source.rejected'));
    await Promise.all([decision(true), phrase().getByRole('button', { name: t('confirm') }).click()]);
    await expect(phrase()).toContainText(t('enums:hit_source.confirmed'));
    await expectObjectScore(page, objectId, 70);
    await expect(riskSummary(page)).toContainText(t('enums:zone.red'));
  } finally {
    try {
      await restorePhrase(api, objectId);
    } finally {
      await api.dispose();
    }
  }
});

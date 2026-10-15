import { expect, type Locator, type Page } from '@playwright/test';
import { t } from './i18n';

export type Zone = 'green' | 'yellow' | 'red';
export const ZONES: Zone[] = ['green', 'yellow', 'red'];

const zoneLabel = (zone: Zone) => t(`enums:zone.${zone}`);

/** The zone counters above the map; each zone is a toggle button with a number in its name. */
export const zoneCounters = (page: Page) => page.getByRole('group', { name: t('map:counters.label') });

export const zoneButton = (page: Page, zone: Zone) =>
  zoneCounters(page).getByRole('button', { name: zoneLabel(zone) });

export async function readCounters(page: Page): Promise<Record<Zone | 'total', number>> {
  const counts = {} as Record<Zone | 'total', number>;
  for (const zone of ZONES) {
    counts[zone] = Number((await zoneButton(page, zone).innerText()).match(/\d+/)?.[0]);
  }
  const text = await zoneCounters(page).innerText();
  const total = new RegExp(`(\\d+)\\s*${t('total')}|${t('total')}\\s*(\\d+)`).exec(text);
  counts.total = Number(total?.[1] ?? total?.[2]);
  return counts;
}

/** Rows of the object list next to the map; their text carries the zone label and the score. */
export const mapObjectRows = (page: Page) =>
  page.getByRole('region', { name: t('map:list.title') }).getByRole('link');

export const scoreOfRow = (rowText: string): number => {
  const match = new RegExp(`(?:${ZONES.map(zoneLabel).join('|')})\\s*(\\d+)`).exec(rowText);
  if (!match) throw new Error(`No zone and score in: ${rowText}`);
  return Number(match[1]);
};

/** The score block of the object card («Риск»). */
export const riskSummary = (page: Page) => page.getByTestId('risk-summary');

export async function readRiskScore(page: Page): Promise<number> {
  const text = await riskSummary(page).innerText();
  const match = /\d+/.exec(text);
  if (!match) throw new Error(`No score in the risk summary: ${text}`);
  return Number(match[0]);
}

/** Picks an item of a select-like control (combobox + option list). */
export async function choose(page: Page, combobox: Locator, option: string | RegExp, search?: string) {
  await combobox.click();
  if (search !== undefined) await combobox.fill(search);
  await page.getByRole('option', { name: option }).click();
}

/** Waits until a page that shows data from the server has loaded it (no loading placeholder is left). */
export async function expectNoLoading(page: Page) {
  await expect(page.getByText(t('loading'))).toHaveCount(0);
}

/** Opens the object card until its score is the expected one (the server recalculates a moment after a change). */
export async function expectObjectScore(page: Page, objectId: number, expected: number | ((score: number) => boolean)) {
  const isExpected = typeof expected === 'number' ? (score: number) => score === expected : expected;
  await expect
    .poll(
      async () => {
        await page.goto(`/objects/${objectId}`);
        await expect(riskSummary(page)).toBeVisible();
        const score = await readRiskScore(page);
        return isExpected(score) ? 'expected' : `score ${score}`;
      },
      { timeout: 90_000, intervals: [1_000, 2_000, 3_000] },
    )
    .toBe('expected');
}

import { test as base, expect, type Browser, type BrowserContext, type Page } from '@playwright/test';
import { BASE_URL } from './env';
import { authFile, type Role } from './users';

/**
 * The suite must not depend on the internet (map tiles, fonts): everything outside the app's origin is refused,
 * and the app falls back to its own offline states.
 */
async function blockExternalRequests(context: BrowserContext) {
  const appOrigin = new URL(BASE_URL).origin;
  await context.route(
    (url) => url.origin !== appOrigin,
    (route) => route.abort(),
  );
}

export const test = base.extend({
  context: async ({ context }, provide) => {
    await blockExternalRequests(context);
    await provide(context);
  },
});

export { expect };

/** A second browser session signed in as another role (for flows that hand work from one user to another). */
export async function openAs(browser: Browser, role: Role): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ storageState: authFile(role), baseURL: BASE_URL, locale: 'ru-RU' });
  await blockExternalRequests(context);
  return { context, page: await context.newPage() };
}

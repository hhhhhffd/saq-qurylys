import { defineConfig, devices } from '@playwright/test';
import { BASE_URL } from './support/env';

/** Isolated UI tests use API route fixtures and never read or write the shared demo database. */
export default defineConfig({
  testDir: './tests',
  testMatch: 'ui-redesign.spec.ts',
  outputDir: '/tmp/saq-ui-after/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: BASE_URL,
    headless: true,
    locale: 'ru-RU',
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});

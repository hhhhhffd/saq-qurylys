import { fileURLToPath } from 'node:url';
import { expect, test } from '../support/test';
import { t } from '../support/i18n';
import { apiAs, findObject } from '../support/api';
import { OBJECT } from '../support/demo';
import { authFile } from '../support/users';
import { choose } from '../support/ui';

test.use({ storageState: authFile('mio') });

const PHOTO = fileURLToPath(new URL('../fixtures/site-photo.jpg', import.meta.url));

// The module is optional: without it the backend answers 404 on the config and the whole spec is skipped.
test.beforeAll(async () => {
  const api = await apiAs('mio');
  const enabled = await api
    .get('/vision/config')
    .then(() => true)
    .catch((error: Error) => !error.message.includes(' 404 '))
    .finally(() => api.dispose());
  test.skip(!enabled, 'the vision module is switched off on this stack');
});

// Not undone: the inspection, its photo and the finding stay in the demo database (see e2e/README.md).
test('a photo is uploaded, an area is marked by hand, confirmed, and the inspection shows on the object card', async ({ page }) => {
  test.setTimeout(150_000);
  const api = await apiAs('mio');
  const object = await findObject(api, OBJECT.birchGrove).finally(() => api.dispose());

  await page.goto('/vision');
  await expect(page.getByRole('link', { name: t('nav.vision') })).toBeVisible();
  await page.getByRole('button', { name: t('vision:create') }).click();
  const dialog = page.getByRole('dialog', { name: t('vision:new.title') });
  await choose(
    page,
    dialog.getByRole('combobox', { name: t('vision:new.object'), exact: true }),
    new RegExp(OBJECT.birchGrove),
    'Берёзовая',
  );
  await dialog.getByRole('button', { name: t('vision:new.submit'), exact: true }).click();
  await expect(page).toHaveURL(/\/vision\/\d+$/);
  await expect(page.getByText(t('vision:banner.detectorOff'), { exact: true })).toBeVisible();

  // The photo is processed by the worker into one frame.
  await page.getByTestId('vision-file-input').setInputFiles(PHOTO);
  const frame = page.getByTestId('vision-frame');
  await expect(frame).toHaveCount(1, { timeout: 60_000 });
  await frame.click();

  // Mark an area of the original frame.
  const viewer = page.getByRole('dialog', { name: t('vision:viewer.title', { label: t('vision:frames.photo') }) });
  await viewer.getByRole('button', { name: t('vision:viewer.draw') }).click();
  const overlay = viewer.getByTestId('vision-frame-overlay');
  await expect(viewer.getByRole('img', { name: /./ })).toBeVisible();
  const box = await overlay.boundingBox();
  if (!box) throw new Error('The frame overlay has no box');
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.4);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.9, box.y + box.height * 0.65, { steps: 5 });
  await page.mouse.up();

  const form = viewer.getByRole('group', { name: t('vision:viewer.newFinding') });
  await choose(page, form.getByRole('combobox', { name: t('vision:finding.category'), exact: true }), t('enums:vision_category.fence'));
  await form.getByRole('textbox', { name: t('vision:finding.note') }).fill('E2E: ограждение с разрывом');
  await form.getByRole('button', { name: t('vision:viewer.saveFinding') }).click();
  await page.keyboard.press('Escape');

  // The finding is in the site block, waits for the analyst and is confirmed by a person.
  const finding = page.getByTestId('vision-finding');
  await expect(finding).toHaveCount(1);
  await expect(finding).toContainText(t('enums:vision_review_state.pending'));
  await finding.getByRole('button', { name: t('vision:finding.actions.confirm'), exact: true }).click();
  await expect(finding).toContainText(t('enums:vision_review_state.confirmed'));

  // The object card lists the inspection.
  await page.goto(`/objects/${object.id}`);
  const panel = page.locator('#vision');
  await expect(panel.getByTestId('vision-card-session').first()).toBeVisible();
});

import { expect, openAs, test } from '../support/test';
import { t } from '../support/i18n';
import { apiAs, closeSignalCards, findObject } from '../support/api';
import { OBJECT } from '../support/demo';
import { authFile } from '../support/users';
import { choose } from '../support/ui';

test.use({ storageState: authFile('mio') });

const NUMBER = /^SQ-\d{4}-\d{4}$/;

// Leaves one closed manual card of «Радужный парк» behind (see e2e/README.md). The automatic cards are not touched.
test('a manual card goes through return, edit, sending to ГАСК, the answer and closing', async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);
  const api = await apiAs('mio');
  const { id: objectId } = await findObject(api, OBJECT.rainbowPark).finally(() => api.dispose());
  // An earlier run that stopped half way would leave an open card, and an object can have only one.
  await closeSignalCards(objectId);

  const status = (code: string) => page.getByText(t(`enums:signal_status.${code}`), { exact: true }).first();
  try {
    // 1. The officer creates the card for a green object.
    await page.goto('/signals');
    await page.getByRole('button', { name: t('signals:list.create') }).click();
    const creation = page.getByRole('dialog', { name: t('signals:create.title') });
    await choose(
      page,
      creation.getByRole('combobox', { name: t('signals:create.object'), exact: true }),
      new RegExp(OBJECT.rainbowPark),
      'Радужный',
    );
    await creation.getByRole('button', { name: t('signals:create.submit'), exact: true }).click();

    await expect(page).toHaveURL(/\/signals\/\d+$/);
    const heading = page.getByRole('heading', { level: 1, name: NUMBER });
    await expect(heading).toBeVisible();
    const number = await heading.innerText();
    await expect(status('requires_confirmation')).toBeVisible();
    await expect(page.getByText(t('enums:origin.manual'), { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: OBJECT.rainbowPark })).toBeVisible();

    // 2. Returns it for rework with a comment.
    const comment = 'E2E: добавьте подтверждение статуса разрешения';
    await page.getByRole('button', { name: t('signals:actions.return') }).click();
    const returning = page.getByRole('dialog', { name: t('signals:actions.return') });
    await returning.getByRole('textbox', { name: t('signals:return.label') }).fill(comment);
    await returning.getByRole('button', { name: t('signals:actions.return') }).click();

    await expect(status('returned')).toBeVisible();
    await expect(page.getByText(t('signals:detail.returnComment'))).toBeVisible();
    // The callout comes before the journal, which repeats the comment among the changes.
    await expect(page.getByText(comment).first()).toBeVisible();

    // 3. Edits it: a note and the route (ГАСК); saving puts the card back to confirmation.
    await page.getByRole('textbox', { name: t('signals:sections.note'), exact: true }).fill('E2E: проверено вручную');
    await choose(
      page,
      page.getByRole('combobox', { name: t('signals:route.recipient'), exact: true }),
      t('enums:recipient.gask'),
    );
    await page.getByRole('button', { name: t('signals:unsaved.save') }).click();
    await expect(status('requires_confirmation')).toBeVisible();
    await expect(page.getByRole('textbox', { name: t('signals:sections.note'), exact: true })).toHaveValue(
      'E2E: проверено вручную',
    );

    // 4. Confirms and sends it to ГАСК.
    await page.getByRole('button', { name: t('signals:actions.confirmSend') }).click();
    const sending = page.getByRole('dialog', { name: t('signals:actions.confirmSend') });
    await expect(sending).toContainText(t('signals:confirmSend.recipient', { recipient: t('enums:recipient.gask') }));
    await expect(sending).toContainText(t('signals:confirmSend.locked'));
    await sending.getByRole('button', { name: t('signals:actions.confirmSend') }).click();

    await expect(status('sent')).toBeVisible();
    await expect(page.getByRole('button', { name: t('signals:actions.confirmSend') })).toHaveCount(0);
    // The journal tells who did what.
    const journal = page.getByRole('heading', { level: 3, name: t('signals:audit.title') });
    await expect(journal).toBeVisible();
    // (The journal also lists old and new values of each change, folded away; only visible entries count.)
    for (const action of ['created', 'returned', 'updated', 'sent']) {
      await expect(page.getByText(t(`signals:audit.actions.${action}`)).filter({ visible: true }).first()).toBeVisible();
    }

    // 5. ГАСК sees the card and records the result.
    const gask = await openAs(browser, 'gask');
    try {
      await gask.page.goto('/signals');
      const row = gask.page.getByRole('row').filter({ hasText: number });
      await expect(row).toContainText(t('enums:recipient.gask'));
      await expect(row).toContainText(t('enums:signal_status.sent'));
      await row.getByRole('link', { name: number }).click();

      await expect(gask.page.getByRole('heading', { level: 1, name: number })).toBeVisible();
      await gask.page.getByRole('button', { name: t('signals:actions.respond') }).click();
      const answering = gask.page.getByRole('dialog', { name: t('signals:actions.respond') });
      const answer = 'E2E: меры приняты, нарушений не выявлено';
      await answering.getByRole('textbox', { name: t('signals:respond.label') }).fill(answer);
      await answering.getByRole('button', { name: t('signals:actions.respond') }).click();

      await expect(gask.page.getByText(t('enums:signal_status.responded'), { exact: true }).first()).toBeVisible();
      await expect(gask.page.getByText(answer).first()).toBeVisible();
      // The registry stays closed for the recipient, and the journal is not shown to it.
      await expect(gask.page.getByRole('heading', { level: 3, name: t('signals:audit.title') })).toHaveCount(0);
    } finally {
      await gask.context.close();
    }

    // 6. The officer sees the answer and closes the card.
    await page.reload();
    await expect(status('responded')).toBeVisible();
    await expect(page.getByText('E2E: меры приняты, нарушений не выявлено').first()).toBeVisible();
    await page.getByRole('button', { name: t('signals:actions.close') }).click();
    await page
      .getByRole('dialog', { name: t('signals:actions.close') })
      .getByRole('button', { name: t('signals:actions.close') })
      .click();
    await expect(status('closed')).toBeVisible();
  } finally {
    // Whatever happened above, the object must not keep an open card.
    await closeSignalCards(objectId);
  }
});

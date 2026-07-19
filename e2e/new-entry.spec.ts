import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test('matches the blank text composer at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await page.goto(routes.newEntry.path);

  await expect(
    page.getByRole('heading', { level: 1, name: routes.newEntry.label }),
  ).toBeVisible();
  await expect(page.getByLabel('Your entry')).toBeEmpty();

  await expect(page).toHaveScreenshot('new-entry-text-desktop.png', {
    fullPage: true,
  });
});

test('matches voice capture without mobile page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await logIn(page);
  await page.goto(routes.newEntry.path);
  await page.getByRole('radio', { name: 'Record' }).click();

  await expect(
    page.getByRole('heading', { name: 'Record a voice entry' }),
  ).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

  await expect(page).toHaveScreenshot('new-entry-voice-mobile.png', {
    fullPage: true,
  });
});

test('keeps unsaved text when navigation is cancelled', async ({ page }) => {
  await logIn(page);
  await page.goto(routes.newEntry.path);
  await page
    .getByLabel('Your entry')
    .fill('A thought that should not disappear accidentally.');

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toBe(
      'Leave this entry? Your unsaved changes will be lost.',
    );
    await dialog.dismiss();
  });
  await page
    .getByRole('navigation', { name: 'breadcrumb' })
    .getByRole('link', { name: routes.entries.label })
    .click();

  await expect(page).toHaveURL(routes.newEntry.path);
  await expect(page.getByLabel('Your entry')).toHaveValue(
    'A thought that should not disappear accidentally.',
  );
});

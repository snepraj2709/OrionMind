import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test('matches the entries list at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await expect(
    page.getByRole('heading', { name: 'July 10, 2025' }),
  ).toBeVisible();

  await expect(page).toHaveScreenshot('entries-desktop.png', {
    fullPage: true,
  });
});

test('matches the entries list without mobile page overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await logIn(page);
  await expect(
    page.getByRole('heading', { name: 'July 10, 2025' }),
  ).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

  await expect(page).toHaveScreenshot('entries-mobile.png', {
    fullPage: true,
  });
});

test('routes from the entries list to a stable detail URL', async ({
  page,
}) => {
  await logIn(page);
  await page.getByRole('link', { name: /July 10, 2025 Complete/ }).click();

  await expect(page).toHaveURL(
    routes.entryDetail.path.replace('[entryId]', 'e1'),
  );
});

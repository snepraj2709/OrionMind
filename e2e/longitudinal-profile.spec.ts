import { expect, test, type Page } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
}

test('matches Journey at desktop and mobile widths', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await page.goto(routes.journey.path);
  await expect(
    page.getByRole('heading', { name: 'Life Theme River' }),
  ).toBeVisible();
  await expect(page).toHaveScreenshot('journey-desktop.png', {
    fullPage: true,
  });

  await page.setViewportSize({ width: 320, height: 900 });
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Life Theme River' }),
  ).toBeVisible();
  await expectNoPageOverflow(page);
  await expect(page).toHaveScreenshot('journey-mobile.png', { fullPage: true });
});

test('matches Profile and preserves accessible form behavior', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await page.goto(routes.profile.path);
  const displayName = page.getByLabel('Display name *');
  await expect(displayName).toHaveValue('Maya Chen');
  await expect(page).toHaveScreenshot('profile-desktop.png', {
    fullPage: true,
  });

  await page.setViewportSize({ width: 320, height: 900 });
  await page.reload();
  await expect(displayName).toHaveValue('Maya Chen');
  await expectNoPageOverflow(page);
  await expect(page).toHaveScreenshot('profile-mobile.png', { fullPage: true });
});

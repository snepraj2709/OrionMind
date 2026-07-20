import { expect, test, type Page } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  const offenders = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('body *')]
      .filter((element) => element.getBoundingClientRect().right > innerWidth)
      .sort(
        (left, right) =>
          right.getBoundingClientRect().right -
          left.getBoundingClientRect().right,
      )
      .slice(0, 8)
      .map((element) => ({
        className: element.className,
        right: element.getBoundingClientRect().right,
        tag: element.tagName,
      })),
  );
  expect(dimensions.content, JSON.stringify(offenders)).toBeLessThanOrEqual(
    dimensions.viewport,
  );
}

test('matches Journey at desktop and mobile widths', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  const journeyResponse = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/api/v1/journey',
  );
  const statusResponse = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/api/v1/journey/status',
  );
  await page.goto(routes.journey.path);
  await expect((await journeyResponse).status()).toBe(200);
  await expect((await statusResponse).status()).toBe(200);
  await expect(
    page.getByRole('heading', { name: 'Not enough data yet' }),
  ).toBeVisible();
  await expect(page.getByRole('radio', { name: 'All' })).toBeChecked();
  await expect(page).toHaveScreenshot('journey-desktop.png', {
    fullPage: true,
  });

  await page.setViewportSize({ width: 320, height: 900 });
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Not enough data yet' }),
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
  await expect(displayName).toHaveValue('reader');
  await expect(page).toHaveScreenshot('profile-desktop.png', {
    fullPage: true,
  });

  await page.setViewportSize({ width: 320, height: 900 });
  await page.reload();
  await expect(displayName).toHaveValue('reader');
  await expectNoPageOverflow(page);
  await expect(page).toHaveScreenshot('profile-mobile.png', { fullPage: true });
});

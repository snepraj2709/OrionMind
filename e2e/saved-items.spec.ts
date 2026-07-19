import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

const screens = [
  { key: 'ideas', route: routes.ideas },
  { key: 'memories', route: routes.memories },
] as const;

for (const screen of screens) {
  test(`matches ${screen.key} at desktop width`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await logIn(page);
    await page.goto(screen.route.path);

    await expect(
      page.getByRole('heading', { level: 1, name: screen.route.label }),
    ).toBeVisible();
    await expect(page.getByText('Saved')).toHaveCount(2);

    await expect(page).toHaveScreenshot(`${screen.key}-desktop.png`, {
      fullPage: true,
    });
  });

  test(`matches ${screen.key} without mobile page overflow`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await logIn(page);
    await page.goto(screen.route.path);
    await expect(page.getByText('Saved')).toHaveCount(2);

    const dimensions = await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

    await expect(page).toHaveScreenshot(`${screen.key}-mobile.png`, {
      fullPage: true,
    });
  });
}

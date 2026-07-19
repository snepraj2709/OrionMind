import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

test('matches Reflections at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await page.goto(routes.reflections.path);

  await expect(
    page.getByRole('heading', { level: 1, name: routes.reflections.label }),
  ).toBeVisible();
  await expect(
    page.getByText(/Patterns taking shape across 23 entries/),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'What seems to drive you' }),
  ).toBeVisible();

  await expect(page).toHaveScreenshot('reflections-desktop.png', {
    fullPage: true,
  });
});

test('matches Reflections without mobile page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await logIn(page);
  await page.goto(routes.reflections.path);

  await expect(
    page.getByRole('heading', { name: 'What seems to drive you' }),
  ).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

  await expect(page).toHaveScreenshot('reflections-mobile.png', {
    fullPage: true,
  });
});

test('reveals evidence intentionally and records rejected insight feedback', async ({
  page,
}) => {
  await logIn(page);
  await page.goto(routes.reflections.path);

  const originalSentence =
    'Explaining a difficult idea to someone else made the whole subject click for me.';
  await expect(page.getByText(originalSentence)).toHaveCount(0);
  await page.getByRole('button', { name: 'View supporting entries' }).click();
  await expect(
    page.getByRole('heading', { name: 'Supporting entries' }),
  ).toBeVisible();
  await expect(page.getByText(originalSentence)).toBeVisible();
  await page.getByRole('button', { name: 'Close' }).click();

  await page.getByRole('button', { name: 'Not true for me' }).click();
  await expect(
    page.getByText(/will not treat this as an accepted self-pattern/),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Not true for me' }),
  ).toHaveAttribute('aria-pressed', 'true');
});

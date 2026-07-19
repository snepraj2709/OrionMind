import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

test('matches the review queue at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await logIn(page);
  await page.goto(routes.approvals.path);

  await expect(
    page.getByRole('heading', { level: 1, name: routes.approvals.label }),
  ).toBeVisible();
  await expect(page.getByText('Needs review')).toHaveCount(3);

  await expect(page).toHaveScreenshot('review-desktop.png', {
    fullPage: true,
  });
});

test('matches the review queue without mobile page overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await logIn(page);
  await page.goto(routes.approvals.path);
  await expect(page.getByText('Needs review')).toHaveCount(3);

  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

  await expect(page).toHaveScreenshot('review-mobile.png', {
    fullPage: true,
  });
});

test('searches, clears, and decides review items', async ({ page }) => {
  await logIn(page);
  await page.goto(routes.approvals.path);

  const search = page.getByRole('searchbox', { name: 'Search review queue' });
  await search.fill('not present');
  await expect(page.getByText('No matching results')).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await expect(page.getByText('Needs review')).toHaveCount(3);

  await page.getByRole('button', { name: 'Approve' }).first().click();
  await expect(page.getByText('Needs review')).toHaveCount(2);
  await expect(page.getByLabel('2 items to review')).toHaveCount(2);

  await page.getByRole('link', { name: routes.ideas.label }).click();
  await expect(
    page.getByText(
      'I want to establish a morning ritual centered on slow, screen-free time before engaging with the day.',
    ),
  ).toBeVisible();
  await page.getByRole('link', { name: 'From July 10, 2025' }).click();
  await expect(page.getByText('Approved')).toBeVisible();
});

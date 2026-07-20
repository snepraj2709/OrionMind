import { expect, test } from '@playwright/test';

import { entryDetailPath } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

test('matches a completed entry detail at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await logIn(page);
  await page.goto(entryDetailPath('e1'));

  await expect(
    page.getByRole('heading', { level: 1, name: 'July 10, 2025' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Themes' })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Extracted items' }),
  ).toBeVisible();

  await expect(page).toHaveScreenshot('entry-detail-desktop.png', {
    fullPage: true,
  });
});

test('matches entry detail without mobile page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await logIn(page);
  await page.goto(entryDetailPath('e1'));
  await expect(page.getByText('Needs review').first()).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

  await expect(page).toHaveScreenshot('entry-detail-mobile.png', {
    fullPage: true,
  });
});

test('reviews an extracted item in place', async ({ page }) => {
  await logIn(page);
  await page.goto(entryDetailPath('e1'));
  await page.getByRole('button', { name: 'Approve' }).first().click();

  await expect(page.getByText('Approved')).toBeVisible();
  await expect(
    page.getByText(
      'I want to establish a morning ritual centered on slow, screen-free time before engaging with the day.',
    ),
  ).toBeVisible();
});

test('keeps failed entry text visible while retrying reflection', async ({
  page,
}) => {
  await logIn(page);
  await page.goto(entryDetailPath('e5'));

  await expect(page.getByText('Reflection did not finish')).toBeVisible();
  await expect(
    page.getByText(/Woke up early. The apartment was very quiet/),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Retry reflection' }).click();

  await expect(
    page.getByText('Orion is reflecting on this entry'),
  ).toBeVisible();
});

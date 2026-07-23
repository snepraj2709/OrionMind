import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import {
  buildEntriesApiResponse,
  entriesApiFixtures,
} from '../src/features/entries';
import { installPendingReviewCountApi } from './helpers/api';
import { logIn } from './helpers/auth';

test.beforeEach(async ({ page }) => {
  await installPendingReviewCountApi(page);
  await page.route('**/api/v1/entries?*', async (route) => {
    const url = new URL(route.request().url());
    const pageNumber = Number(url.searchParams.get('page') ?? '1');
    const pageSize = Number(url.searchParams.get('page_size') ?? '10');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        buildEntriesApiResponse({
          entries: entriesApiFixtures,
          page: pageNumber,
          page_size: pageSize,
        }),
      ),
    });
  });
});

test('matches the entries list at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await expect(
    page.getByRole('link', { name: /10 Jul/ }).first(),
  ).toBeVisible();
  await page.mouse.move(0, 0);

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
    page.getByRole('link', { name: /10 Jul/ }).first(),
  ).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
  await page.mouse.move(0, 0);

  await expect(page).toHaveScreenshot('entries-mobile.png', {
    fullPage: true,
  });
});

test('routes from the entries list to a stable detail URL', async ({
  page,
}) => {
  await logIn(page);
  await page
    .getByRole('link', { name: /10 Jul/ })
    .first()
    .click();

  await expect(page).toHaveURL(
    routes.entryDetail.path.replace('[entryId]', 'e1'),
  );
});

test('shows only backend-supported fixed pagination controls', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await expect(
    page.getByRole('link', { name: /10 Jul/ }).first(),
  ).toBeVisible();

  await expect(
    page.getByRole('searchbox', { name: 'Search entries' }),
  ).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Status' })).toHaveCount(0);
  await expect(
    page.getByRole('combobox', { name: 'Rows per page' }),
  ).toHaveCount(0);
  await expect(page.getByText('Page 1 of 1')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Prev' })).toBeDisabled();
  await expect(
    page.getByRole('button', { name: 'Next', exact: true }),
  ).toBeDisabled();
});

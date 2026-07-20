import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

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

test('submits search explicitly and uses fixed minimal pagination', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);
  await expect(
    page.getByRole('link', { name: /10 Jul/ }).first(),
  ).toBeVisible();

  const search = page.getByRole('searchbox', { name: 'Search entries' });
  await search.fill('canal');
  await expect(page.getByRole('link', { name: /10 Jul/ })).toBeVisible();
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByRole('link', { name: /7 Jul/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /10 Jul/ })).toHaveCount(0);
  await search.clear();
  await search.press('Enter');

  await page.getByRole('combobox', { name: 'Status' }).click();
  await page.getByRole('option', { name: 'Processing', exact: true }).click();
  await expect(page.getByRole('link', { name: /7 Jul/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /10 Jul/ })).toHaveCount(0);

  await page.getByRole('combobox', { name: 'Status' }).click();
  await page.getByRole('option', { name: 'All entries' }).click();
  await expect(page.getByRole('link', { name: /10 Jul/ })).toBeVisible();

  await expect(
    page.getByRole('combobox', { name: 'Rows per page' }),
  ).toHaveCount(0);
  await expect(page.getByText('Page 1 of 1')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Prev' })).toBeDisabled();
  await expect(
    page.getByRole('button', { name: 'Next', exact: true }),
  ).toBeDisabled();
});

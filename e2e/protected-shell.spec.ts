import { expect, test } from '@playwright/test';

import { logIn } from './helpers/auth';

test('matches the protected desktop shell', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await logIn(page);

  const navigation = page.getByRole('navigation', {
    name: 'Primary navigation',
  });
  await expect(
    navigation.getByRole('link', { name: 'Entries' }),
  ).toHaveAttribute('aria-current', 'page');
  await expect(navigation.getByLabel('6 items to review')).toBeVisible();

  await expect(page.getByLabel('Primary navigation sidebar')).toHaveScreenshot(
    'protected-shell-desktop.png',
  );
});

test('matches the protected mobile navigation sheet', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await logIn(page);
  await page.getByRole('button', { name: 'Open navigation' }).click();

  const navigation = page.getByRole('navigation', {
    name: 'Mobile navigation',
  });
  await expect(navigation.getByRole('link', { name: 'Entries' })).toBeVisible();
  await expect(navigation.getByLabel('6 items to review')).toBeVisible();

  await expect(page.getByRole('dialog')).toHaveScreenshot(
    'protected-shell-mobile.png',
  );
});

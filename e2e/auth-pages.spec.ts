import { expect, test, type Page } from '@playwright/test';

import { routes } from '../src/config/routes';

const authPages = [
  {
    key: 'login',
    path: routes.login.path,
    heading: 'Welcome back',
  },
  {
    key: 'signup',
    path: routes.signup.path,
    heading: 'Begin your journal',
  },
] as const;

async function waitForFonts(page: Page) {
  await page.evaluate(() => document.fonts.ready);
}

for (const authPage of authPages) {
  test(`matches ${authPage.key} at desktop width`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(authPage.path);
    await waitForFonts(page);

    await expect(
      page.getByRole('heading', { level: 1, name: authPage.heading }),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Orion' })).toBeVisible();
    await expect(page).toHaveScreenshot(`${authPage.key}-desktop.png`, {
      animations: 'disabled',
    });
  });

  test(`matches ${authPage.key} without mobile overflow`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto(authPage.path);
    await waitForFonts(page);

    const pageSize = await page.evaluate(() => ({
      contentHeight: document.documentElement.scrollHeight,
      contentWidth: document.documentElement.scrollWidth,
      viewportHeight: window.innerHeight,
      viewportWidth: document.documentElement.clientWidth,
    }));

    expect(pageSize.contentWidth).toBeLessThanOrEqual(pageSize.viewportWidth);
    expect(pageSize.contentHeight).toBeLessThanOrEqual(pageSize.viewportHeight);
    await expect(page).toHaveScreenshot(`${authPage.key}-mobile.png`, {
      animations: 'disabled',
    });
  });
}

test('keeps the login form in a logical keyboard order', async ({ page }) => {
  await page.goto(routes.login.path);

  await page.getByRole('link', { name: 'Orion' }).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Email *')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Password *')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('link', { name: 'Forgot password?' }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeFocused();
});

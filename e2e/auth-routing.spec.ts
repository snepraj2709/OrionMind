import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { installPendingReviewCountApi } from './helpers/api';
import {
  installMockSupabaseAuth,
  logIn,
  testCredentials,
} from './helpers/auth';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        error_code: 'SERVICE_UNAVAILABLE',
        message: 'The deterministic routing test does not provide data APIs.',
        details: {},
        request_id: 'e2e-routing-test',
      }),
    }),
  );
  await installPendingReviewCountApi(page);
});

test('serves the canonical logo and a valid favicon', async ({ request }) => {
  const logo = await request.get('/images/light-mode-transparent.svg');
  expect(logo.ok()).toBe(true);
  expect(logo.headers()['content-type']).toContain('image/svg+xml');

  const favicon = await request.get('/favicon.ico');
  expect(favicon.ok()).toBe(true);
  expect(favicon.headers()['content-type']).toContain('image/x-icon');
  expect(Array.from((await favicon.body()).subarray(0, 4))).toEqual([
    0x00, 0x00, 0x01, 0x00,
  ]);
});

test('loads the public landing route without runtime errors', async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto(routes.home.path);
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL(routes.home.path);
  await expect(
    page.getByRole('heading', {
      name: 'Connect the dots in your thoughts.',
    }),
  ).toBeVisible();
  await expect(page.getByText('Something went wrong')).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});

test('keeps the landing-page top bar in normal document flow', async ({
  page,
}) => {
  await page.goto(routes.home.path);
  await page.waitForLoadState('networkidle');

  const banner = page.getByRole('banner');
  await expect(banner).toHaveCount(1);
  await expect(banner).toHaveCSS('position', 'static');
});

test('keeps password recovery on the public login route', async ({ page }) => {
  await page.goto(routes.login.path);
  await page.getByRole('link', { name: 'Forgot password?' }).click();

  await expect(
    page.getByRole('heading', { name: 'Reset your password' }),
  ).toBeVisible();
  await expect(page).toHaveURL(`${routes.login.path}?mode=forgot`);
});

test('hydrates the configured login route without recoverable errors', async ({
  page,
}) => {
  const browserErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });
  page.on('pageerror', (error) => browserErrors.push(error.message));

  await page.goto(routes.login.path);
  await page.waitForLoadState('networkidle');

  await expect(
    page.getByRole('heading', { name: 'Welcome back' }),
  ).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('loads the mobile landing route without runtime errors or overflow', async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto(routes.home.path);
  await page.waitForLoadState('networkidle');

  await expect(
    page.getByRole('heading', {
      name: 'Connect the dots in your thoughts.',
    }),
  ).toBeVisible();
  await expect(page.getByText('Something went wrong')).toHaveCount(0);

  const pageWidth = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));

  expect(pageWidth.content).toBeLessThanOrEqual(pageWidth.viewport);

  expect(pageErrors).toEqual([]);
});

test('uses the document as the only landing-page vertical scroller', async ({
  page,
}) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 768, height: 900 },
    { width: 320, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(routes.home.path);
    await page.waitForLoadState('networkidle');

    const result = await page.evaluate(() => {
      const nestedVerticalScrollContainers = Array.from(
        document.querySelectorAll<HTMLElement>('*'),
      )
        .filter((element) => {
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return (
            style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            rect.width > 0 &&
            rect.height > 0 &&
            ['auto', 'scroll'].includes(style.overflowY) &&
            element.scrollHeight > element.clientHeight + 1
          );
        })
        .map((element) => ({
          tag: element.tagName.toLowerCase(),
          className:
            typeof element.className === 'string' ? element.className : '',
        }));
      return {
        behavior: getComputedStyle(document.documentElement).scrollBehavior,
        documentScroller: document.scrollingElement?.tagName.toLowerCase(),
        nestedVerticalScrollContainers,
      };
    });

    expect(result.behavior).toBe('auto');
    expect(result.documentScroller).toBe('html');
    expect(result.nestedVerticalScrollContainers).toEqual([]);
  }
});

test('keeps wheel input authoritative after section navigation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(routes.home.path);
  await page.waitForLoadState('networkidle');

  await page
    .locator('a[href="#how-it-works"]')
    .first()
    .evaluate((link: HTMLAnchorElement) => link.click());
  await page.waitForTimeout(100);
  const beforeWheel = await page.evaluate(() => window.scrollY);
  await page.mouse.move(720, 450);
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(150);
  const afterWheel = await page.evaluate(() => window.scrollY);

  expect(afterWheel).toBeGreaterThan(beforeWheel);
});

test('redirects protected routes to login', async ({ page }) => {
  await page.goto(routes.entries.path);

  await expect(page).toHaveURL(`${routes.login.path}?returnTo=%2Fentries`);
});

test('logs in and redirects authenticated users away from login', async ({
  page,
}) => {
  await page.goto(routes.login.path);
  await expect(page.locator('form')).toHaveAttribute('method', 'post');

  await logIn(page);

  await expect(
    page.getByRole('heading', { name: routes.entries.label }),
  ).toBeVisible();

  await page.goto(routes.login.path);
  await expect(page).toHaveURL(routes.entries.path);
});

test('shows email confirmation after signup', async ({ page }) => {
  await installMockSupabaseAuth(page);
  await page.goto(routes.signup.path);
  await page.getByLabel('Email').fill(testCredentials.email);
  await page
    .getByRole('textbox', { name: 'Password', exact: true })
    .fill(testCredentials.password);
  await page.getByRole('button', { name: 'Create account' }).click();

  await expect(page.getByRole('status')).toContainText(
    'Open the newest confirmation link',
  );
  await expect(page).toHaveURL(routes.signup.path);
});

test('logs out from the protected shell', async ({ page }) => {
  await logIn(page);
  await page.getByRole('button', { name: 'Log out' }).click();

  await expect(page).toHaveURL(`${routes.login.path}?returnTo=%2Fentries`);
  await page.goto(routes.entries.path);
  await expect(page).toHaveURL(`${routes.login.path}?returnTo=%2Fentries`);
});

test('returns a successful login to the protected destination', async ({
  page,
}) => {
  await page.goto(routes.newEntry.path);
  await expect(page).toHaveURL(
    `${routes.login.path}?returnTo=%2Fentries%2Fnew`,
  );

  await installMockSupabaseAuth(page);

  await page.getByLabel('Email').fill(testCredentials.email);
  await page
    .getByRole('textbox', { name: 'Password', exact: true })
    .fill(testCredentials.password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(routes.newEntry.path);
  await expect(
    page.getByRole('heading', { name: routes.newEntry.label }),
  ).toBeVisible();
});

test('moves between authentication routes without a protected redirect', async ({
  page,
}) => {
  await page.goto(routes.newEntry.path);
  await page.getByRole('link', { name: 'Register' }).click();

  await expect(page).toHaveURL(routes.signup.path);
  await expect(
    page.getByRole('heading', { name: 'Begin your journal' }),
  ).toBeVisible();
});

test('closes mobile navigation after route changes', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await logIn(page);
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page
    .getByRole('dialog')
    .getByRole('link', { name: routes.reflections.label })
    .click();

  await expect(page).toHaveURL(routes.reflections.path);
  await expect(page.getByRole('dialog')).toBeHidden();
});

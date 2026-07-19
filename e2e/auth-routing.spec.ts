import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import { logIn, testCredentials } from './helpers/auth';

test('allows public route access', async ({ page }) => {
  await page.goto(routes.home.path);
  await expect(page).toHaveURL(routes.home.path);
  await expect(
    page.getByRole('heading', {
      name: 'A place to see your subconscious and what it might be be telling about you.',
    }),
  ).toBeVisible();

  const createAccountLinks = page.getByRole('link', {
    name: 'Create account',
  });
  await expect(createAccountLinks).toHaveCount(3);
  for (const link of await createAccountLinks.all()) {
    await expect(link).toHaveAttribute('href', routes.signup.path);
  }

  await page.goto(routes.forgotPassword.path);

  await expect(
    page.getByRole('heading', { name: routes.forgotPassword.label }),
  ).toBeVisible();
});

test('keeps every landing action available without mobile overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto(routes.home.path);

  await expect(
    page.getByRole('heading', {
      name: 'A place to see your subconscious and what it might be be telling about you.',
    }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Create account' })).toHaveCount(
    3,
  );

  const pageWidth = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));

  expect(pageWidth.content).toBeLessThanOrEqual(pageWidth.viewport);

  const viewportSections = await page
    .locator('[data-viewport-section]')
    .evaluateAll((sections) =>
      sections.map((section) => ({
        height: section.getBoundingClientRect().height,
        contentHeight: section.scrollHeight,
      })),
    );

  expect(viewportSections).toHaveLength(3);
  for (const section of viewportSections) {
    expect(section.height).toBeGreaterThanOrEqual(900);
    expect(section.contentHeight).toBeLessThanOrEqual(section.height);
  }

  const footer = page.getByRole('contentinfo');
  await expect(
    footer.getByRole('heading', {
      name: 'Begin reflecting to see the unseen.',
    }),
  ).toBeVisible();
  await expect(footer.getByRole('link', { name: 'Twitter / X' })).toBeVisible();
  await expect(footer.getByRole('link', { name: 'LinkedIn' })).toBeVisible();
  await expect(footer.getByRole('link', { name: 'Instagram' })).toBeVisible();
});

test('redirects protected routes to login', async ({ page }) => {
  await page.goto(routes.entries.path);

  await expect(page).toHaveURL(
    new RegExp(`${routes.login.path}\\?redirect=%2Fentries$`),
  );
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

test('signs up a new mock user', async ({ page }) => {
  await page.goto(routes.signup.path);
  await page.getByLabel('Full name').fill('Orion Reader');
  await page.getByLabel('Email').fill('new-reader@example.com');
  await page.getByLabel('Password').fill(testCredentials.password);
  await page.getByRole('button', { name: 'Create account' }).click();

  await expect(page).toHaveURL(routes.entries.path);
  await expect(page.getByText('Orion Reader')).toBeVisible();
});

test('logs out from the protected shell', async ({ page }) => {
  await logIn(page);
  await page.getByRole('button', { name: 'Log out' }).click();

  await expect(page).toHaveURL(routes.login.path);
  await page.goto(routes.entries.path);
  await expect(page).toHaveURL(
    new RegExp(`${routes.login.path}\\?redirect=%2Fentries$`),
  );
});

test('returns to the requested protected destination after login', async ({
  page,
}) => {
  await page.goto(routes.newEntry.path);
  await expect(page).toHaveURL(
    new RegExp(`${routes.login.path}\\?redirect=%2Fentries%2Fnew$`),
  );

  await page.getByLabel('Email').fill(testCredentials.email);
  await page.getByLabel('Password').fill(testCredentials.password);
  await page.getByRole('button', { name: 'Log in' }).click();

  await expect(page).toHaveURL(routes.newEntry.path);
  await expect(
    page.getByRole('heading', { name: routes.newEntry.label }),
  ).toBeVisible();
});

test('preserves the requested destination across authentication routes', async ({
  page,
}) => {
  await page.goto(routes.newEntry.path);
  await page.getByRole('link', { name: 'Create an account' }).click();

  await expect(page).toHaveURL(
    new RegExp(`${routes.signup.path}\\?redirect=%2Fentries%2Fnew$`),
  );

  await page.getByLabel('Full name').fill('Redirected Reader');
  await page.getByLabel('Email').fill('redirected@example.com');
  await page.getByLabel('Password').fill(testCredentials.password);
  await page.getByRole('button', { name: 'Create account' }).click();

  await expect(page).toHaveURL(routes.newEntry.path);
});

test('closes mobile navigation after route changes', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await logIn(page);
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page
    .getByRole('dialog')
    .getByRole('link', { name: routes.ideas.label })
    .click();

  await expect(page).toHaveURL(routes.ideas.path);
  await expect(page.getByRole('dialog')).toBeHidden();
});

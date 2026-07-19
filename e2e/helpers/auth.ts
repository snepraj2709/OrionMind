import { expect, type Page } from '@playwright/test';

import { routes } from '../../src/config/routes';

export const testCredentials = {
  email: 'reader@example.com',
  password: 'calm-space-2026',
};

export async function logIn(page: Page) {
  await page.goto(routes.login.path);
  await page.getByLabel('Email').fill(testCredentials.email);
  await page.getByLabel('Password').fill(testCredentials.password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL(routes.entries.path);
}

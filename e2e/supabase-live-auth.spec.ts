import { expect, test } from '@playwright/test';

import { routes } from '../src/config/routes';
import {
  getRequiredTestEnvironmentVariable,
  liveTestCredentials,
} from './helpers/auth';

test.use({ trace: 'off' });

test('uses live Supabase auth and sends its bearer token to the configured API', async ({
  page,
}) => {
  const apiBaseUrl = getRequiredTestEnvironmentVariable(
    'NEXT_PUBLIC_API_BASE_URL',
  ).replace(/\/+$/, '');
  const entriesApiUrl = `${apiBaseUrl}/api/v1/entries`;
  const apiRequest = page.waitForRequest((request) =>
    request.url().startsWith(entriesApiUrl),
  );

  await page.goto(routes.login.path);
  await page.getByLabel('Email').fill(liveTestCredentials.email);
  await page.getByLabel('Password').fill(liveTestCredentials.password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(routes.entries.path);
  const request = await apiRequest;
  expect(request.method()).toBe('GET');
  expect(request.postData()).toBeNull();
  expect(/^Bearer\s+\S+$/.test(request.headers().authorization ?? '')).toBe(
    true,
  );
  const apiResponse = await request.response();
  expect(apiResponse !== null).toBe(true);
  expect(apiResponse?.status()).toBe(200);

  const storageKeys = await page.evaluate(() => Object.keys(sessionStorage));
  expect(storageKeys.some((key) => key.startsWith('sb-'))).toBe(true);
  expect(storageKeys.some((key) => key.startsWith('orion'))).toBe(false);

  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page).toHaveURL(/\/login(?:\?|$)/);
});

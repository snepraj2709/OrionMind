import { expect, type Page } from '@playwright/test';
import { createClient, type Session } from '@supabase/supabase-js';

import { routes } from '../../src/config/routes';

export function getRequiredTestEnvironmentVariable(name: string) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required for authenticated tests.`);
  return value;
}

export const testCredentials = {
  email: getRequiredTestEnvironmentVariable('SUPABASE_TEST_EMAIL'),
  password: getRequiredTestEnvironmentVariable('SUPABASE_TEST_PASSWORD'),
};

let testSessionPromise: Promise<Session> | undefined;

function getTestSession() {
  testSessionPromise ??= (async () => {
    const client = createClient(
      getRequiredTestEnvironmentVariable('NEXT_PUBLIC_SUPABASE_URL'),
      getRequiredTestEnvironmentVariable(
        'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY',
      ),
      {
        auth: {
          autoRefreshToken: false,
          detectSessionInUrl: false,
          persistSession: false,
        },
      },
    );
    const { data, error } =
      await client.auth.signInWithPassword(testCredentials);
    if (error || !data.session) {
      throw new Error('The Supabase test account could not sign in.');
    }
    return data.session;
  })();

  return testSessionPromise;
}

export async function installMockSupabaseAuth(page: Page) {
  const supabaseUrl = getRequiredTestEnvironmentVariable(
    'NEXT_PUBLIC_SUPABASE_URL',
  );
  const userId = '00000000-0000-4000-8000-000000000001';
  const timestamp = new Date().toISOString();

  await page.route(`${supabaseUrl}/auth/v1/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname.endsWith('/token')) {
      const body = request.postDataJSON() as {
        email?: string;
        password?: string;
      };
      if (
        body.email !== testCredentials.email ||
        body.password !== testCredentials.password
      ) {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 'invalid_credentials',
            message: 'Invalid login credentials',
          }),
        });
        return;
      }

      const session = await getTestSession();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(session),
      });
      return;
    }

    if (url.pathname.endsWith('/signup')) {
      const body = request.postDataJSON() as {
        data?: { full_name?: string };
        email?: string;
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: null,
          refresh_token: null,
          user: {
            id: userId,
            aud: 'authenticated',
            role: 'authenticated',
            email: body.email,
            app_metadata: { provider: 'email', providers: ['email'] },
            user_metadata: { full_name: body.data?.full_name },
            identities: [],
            created_at: timestamp,
            updated_at: timestamp,
            is_anonymous: false,
          },
        }),
      });
      return;
    }

    if (url.pathname.endsWith('/logout')) {
      await route.fulfill({ status: 204, body: '' });
      return;
    }

    await route.continue();
  });
}

export async function logIn(page: Page) {
  await installMockSupabaseAuth(page);
  await page.goto(routes.login.path);
  await page.getByLabel('Email').fill(testCredentials.email);
  await page.getByLabel('Password').fill(testCredentials.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(routes.entries.path);
}

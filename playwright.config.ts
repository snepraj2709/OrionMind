import { defineConfig, devices } from '@playwright/test';
import { loadEnvConfig } from '@next/env';
import path from 'node:path';

const backendTestEnvironment = loadEnvConfig(
  path.join(process.cwd(), 'backend'),
).combinedEnv;
const testEmail = backendTestEnvironment.SUPABASE_TEST_EMAIL2;
const testPassword = backendTestEnvironment.SUPABASE_TEST_PASSWORD2;
loadEnvConfig(process.cwd(), false, console, true);
if (testEmail) process.env.SUPABASE_TEST_EMAIL2 = testEmail;
if (testPassword) process.env.SUPABASE_TEST_PASSWORD2 = testPassword;

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3100';
const usesExternalServer = Boolean(process.env.PLAYWRIGHT_BASE_URL);

export default defineConfig({
  testDir: './e2e',
  testIgnore: 'review-reflection-flow.spec.ts',
  // Mock repositories share one process-local store. Keep route tests isolated
  // until backend persistence scopes records to the authenticated user.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL,
    // The dedicated live-auth spec uses real test credentials. Never persist
    // its password, access token, refresh token, or session in trace artifacts.
    trace: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: usesExternalServer
    ? undefined
    : {
        command: 'npm run build && npm run start -- --port 3100',
        env: { NEXT_PUBLIC_REFLECTIONS_ENABLED: 'true' },
        timeout: 120_000,
        url: `${baseURL}/api/health`,
        reuseExistingServer: !process.env.CI,
      },
});

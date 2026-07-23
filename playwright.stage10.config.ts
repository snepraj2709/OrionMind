import { defineConfig, devices } from '@playwright/test';
import { loadEnvConfig } from '@next/env';

loadEnvConfig(process.cwd());

const baseURL = 'http://127.0.0.1:3101';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'review-reflection-flow.spec.ts',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    trace: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run build && npm run start -- --port 3101',
    env: {
      NEXT_PUBLIC_API_BASE_URL: 'http://127.0.0.1:18080',
      NEXT_PUBLIC_REFLECTIONS_ENABLED: 'true',
    },
    timeout: 120_000,
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
  },
});

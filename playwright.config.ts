import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3100';
const usesExternalServer = Boolean(process.env.PLAYWRIGHT_BASE_URL);

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL,
    trace: 'on-first-retry',
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
        env: {
          ORION_MOCK_AUTH_SECRET: 'orion-playwright-mock-auth-only',
        },
        timeout: 120_000,
        url: `${baseURL}/api/health`,
        reuseExistingServer: !process.env.CI,
      },
});

import { expect, test, type Page } from '@playwright/test';

import { entryDetailPath } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

const entryId = '8a7cc7df-94e5-41b4-b983-ab6ddda47785';
const failedEntryId = '27cf52b5-a015-427e-b7b5-914af00d19ee';
const themeConfigId = '046870f3-a50f-4406-a9d8-36e774a793f1';

const completedDetail = {
  id: entryId,
  content:
    'This morning I sat with my coffee longer than usual, watching the light change across the kitchen wall. There was something in that stillness — a kind of permission to exist without producing anything.',
  input_type: 'text',
  entry_date: '2025-07-10',
  original_theme_config_id: themeConfigId,
  processing_status: 'completed',
  processing_error_code: null,
  created_at: '2025-07-10T08:30:00Z',
  classification: {
    theme_config_id: themeConfigId,
    source: 'initial',
    mode: 'balanced',
    themes: [
      {
        key: 'personal_growth',
        name: 'Personal Growth',
        score: 0.9,
        tier: 'primary',
      },
      {
        key: 'health',
        name: 'Health',
        score: 0.7,
        tier: 'secondary',
      },
      {
        key: 'family_friends',
        name: 'Family and Friends',
        score: 0.5,
        tier: 'tertiary',
      },
    ],
  },
  ideas: [
    {
      id: '9c36b3da-85da-4b63-93ee-5a48dc289034',
      content:
        'I want to establish a morning ritual centered on slow, screen-free time before engaging with the day.',
      status: 'pending_approval',
      entry_id: entryId,
      entry_date: '2025-07-10',
      created_at: '2025-07-10T08:31:00Z',
      decided_at: null,
    },
  ],
  extracted_memories: [],
  reflections: [
    {
      id: '9f01fe2c-6a51-4aaf-844e-46495cba87ce',
      reflection_type: 'learned_about_self',
      activity:
        'Slow, unstructured mornings help me hear what I need before the day starts asking things of me.',
      confidence_score: 0.9,
      status: 'pending_approval',
      entry_id: entryId,
      entry_date: '2025-07-10',
      created_at: '2025-07-10T08:31:00Z',
      decided_at: null,
    },
  ],
};

const failedDetail = {
  ...completedDetail,
  id: failedEntryId,
  content:
    'Woke up early. The apartment was very quiet. Made tea and sat on the floor, reading old journal entries from two years ago.',
  input_type: 'audio',
  entry_date: '2025-07-04',
  processing_status: 'failed',
  processing_error_code: 'PROCESSING_PROVIDER_FAILURE',
  classification: null,
  ideas: [],
  reflections: [],
};

interface DetailCall {
  authorization?: string;
  body: string | null;
  method: string;
  path: string;
}

async function interceptEntryDetailBackend(page: Page) {
  const calls: DetailCall[] = [];
  await page.route('**/api/v1/entries/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    calls.push({
      authorization: request.headers().authorization,
      body: request.postData(),
      method: request.method(),
      path,
    });
    const isRetry = path.endsWith('/retry');
    const detail = path.includes(failedEntryId)
      ? failedDetail
      : completedDetail;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        isRetry
          ? {
              ...detail,
              processing_status: 'pending',
              processing_error_code: null,
            }
          : detail,
      ),
    });
  });
  return calls;
}

test('matches a completed entry detail at desktop width', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await interceptEntryDetailBackend(page);
  await logIn(page);
  await page.goto(entryDetailPath('e1'));

  await expect(
    page.getByRole('heading', { level: 1, name: 'July 10, 2025' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Themes' })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Extracted items' }),
  ).toBeVisible();

  await expect(page).toHaveScreenshot('entry-detail-desktop.png', {
    fullPage: true,
  });
});

test('matches entry detail without mobile page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await interceptEntryDetailBackend(page);
  await logIn(page);
  await page.goto(entryDetailPath('e1'));
  await expect(page.getByText('Needs review').first()).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);

  await expect(page).toHaveScreenshot('entry-detail-mobile.png', {
    fullPage: true,
  });
});

test('renders extracted items as read-only', async ({ page }) => {
  await interceptEntryDetailBackend(page);
  await logIn(page);
  await page.goto(entryDetailPath('e1'));

  await expect(
    page.getByText(
      'I want to establish a morning ritual centered on slow, screen-free time before engaging with the day.',
    ),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approve' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Reject' })).toHaveCount(0);
});

test('uses authenticated GET and bodyless retry requests', async ({ page }) => {
  const calls = await interceptEntryDetailBackend(page);
  await logIn(page);
  await page.goto(entryDetailPath(failedEntryId));

  await expect(page.getByText('Reflection did not finish')).toBeVisible();
  await expect(
    page.getByText(/Woke up early. The apartment was very quiet/),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Retry reflection' }).click();

  await expect(page.getByText('Entry is queued for reflection')).toBeVisible();
  expect(calls).toHaveLength(2);
  expect(calls[0]).toMatchObject({
    body: null,
    method: 'GET',
    path: `/api/v1/entries/${failedEntryId}`,
  });
  expect(calls[1]).toMatchObject({
    body: null,
    method: 'POST',
    path: `/api/v1/entries/${failedEntryId}/retry`,
  });
  expect(calls[0]?.authorization).toMatch(/^Bearer /);
  expect(calls[1]?.authorization).toMatch(/^Bearer /);
});

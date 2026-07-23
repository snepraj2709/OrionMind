import { expect, test, type Page } from '@playwright/test';

import type {
  ReviewFeedbackRequest,
  ReviewItem,
  ReviewStatus,
} from '../src/features/review';
import { routes } from '../src/config/routes';

test.describe.configure({ mode: 'serial' });

function encodedJson(value: unknown) {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

async function logIn(page: Page) {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  if (!supabaseUrl) {
    throw new Error('NEXT_PUBLIC_SUPABASE_URL is required for browser tests.');
  }
  const userId = '80000000-0000-4000-8000-000000000001';
  const now = Math.floor(Date.now() / 1000);
  const accessToken = [
    encodedJson({ alg: 'HS256', typ: 'JWT' }),
    encodedJson({
      aud: 'authenticated',
      exp: now + 3600,
      iat: now,
      sub: userId,
      email: 'review-e2e@example.com',
      role: 'authenticated',
      aal: 'aal1',
      session_id: 'review-e2e-session',
      is_anonymous: false,
      app_metadata: { provider: 'email', providers: ['email'] },
      user_metadata: { full_name: 'Review E2E' },
    }),
    'review-e2e-signature',
  ].join('.');
  const user = {
    id: userId,
    aud: 'authenticated',
    role: 'authenticated',
    email: 'review-e2e@example.com',
    app_metadata: { provider: 'email', providers: ['email'] },
    user_metadata: { full_name: 'Review E2E' },
    identities: [],
    created_at: new Date(now * 1000).toISOString(),
    updated_at: new Date(now * 1000).toISOString(),
    is_anonymous: false,
  };

  await page.route(`${supabaseUrl}/auth/v1/**`, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/token')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: accessToken,
          refresh_token: 'review-e2e-refresh-token',
          expires_in: 3600,
          expires_at: now + 3600,
          token_type: 'bearer',
          user,
        }),
      });
      return;
    }
    await route.fulfill({ status: 204, body: '' });
  });

  await page.goto(routes.login.path);
  await page.getByLabel('Email').fill('review-e2e@example.com');
  await page.getByLabel('Password').fill('review-e2e-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(routes.entries.path);
}

const entryItem: ReviewItem = {
  id: '81111111-1111-4111-8111-111111111111',
  scope: 'entry_insight',
  type: 'energy_loss',
  category: 'energy',
  statement: 'Preparing at the last minute drains my energy.',
  sourceQuote: 'The rushed preparation was exhausting.',
  sourceEntryIds: ['82222222-2222-4222-8222-222222222222'],
  sourceDates: ['2026-07-20'],
  inferenceLevel: 'direct',
  confidence: 0.94,
  status: 'pending',
  feedback: null,
};

const patternItem: ReviewItem = {
  id: '83333333-3333-4333-8333-333333333333',
  scope: 'pattern',
  type: 'hidden_driver',
  category: 'hidden_driver',
  statement: 'Perfection may protect me from being evaluated.',
  sourceQuote: null,
  sourceEntryIds: [
    '84444444-4444-4444-8444-444444444444',
    '85555555-5555-4555-8555-555555555555',
  ],
  sourceDates: ['2026-07-04', '2026-07-08'],
  inferenceLevel: 'synthesized',
  confidence: 0.82,
  status: 'pending',
  feedback: null,
};

function feedbackResult(
  item: ReviewItem,
  feedback: ReviewFeedbackRequest,
): ReviewItem {
  const confirmed = ['accurate', 'resonates'].includes(feedback.verdict);
  const partial = ['partly_accurate', 'partly_true'].includes(feedback.verdict);
  const status: ReviewStatus = confirmed
    ? 'confirmed'
    : partial
      ? 'partially_confirmed'
      : 'rejected';
  const evidenceWeight = confirmed ? 1 : partial ? 0.5 : 0;
  return {
    ...item,
    status,
    feedback: {
      ...feedback,
      correctedStatement: feedback.correctedStatement?.trim() || null,
      note: feedback.note?.trim() || null,
      evidenceWeight,
      updatedAt: '2026-07-23T10:30:00Z',
    },
  } as ReviewItem;
}

async function installReviewApi(
  page: Page,
  options: { empty?: boolean; fail?: boolean } = {},
) {
  let items = options.empty ? [] : [entryItem, patternItem];
  const requests: Array<{
    method: string;
    path: string;
    body?: unknown;
  }> = [];

  await page.route('**/api/v1/review/items**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = method === 'POST' ? request.postDataJSON() : undefined;
    requests.push({ method, path: `${url.pathname}${url.search}`, body });

    if (options.fail) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error_code: 'SERVICE_UNAVAILABLE',
          message: 'The service is temporarily unavailable.',
          details: {},
          request_id: 'review-e2e',
        }),
      });
      return;
    }

    if (method === 'POST') {
      const itemId = url.pathname.split('/').at(-2);
      const item = items.find((candidate) => candidate.id === itemId);
      if (!item) {
        await route.fulfill({ status: 404, body: '' });
        return;
      }
      const updated = feedbackResult(item, body as ReviewFeedbackRequest);
      items = items.map((candidate) =>
        candidate.id === updated.id ? updated : candidate,
      );
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Cache-Control': 'private, no-store' },
        body: JSON.stringify(updated),
      });
      return;
    }

    const scope = url.searchParams.get('scope');
    const category = url.searchParams.get('category');
    const status = url.searchParams.get('status');
    const pageNumber = Number(url.searchParams.get('page') ?? '1');
    const pageSize = Number(url.searchParams.get('page_size') ?? '20');
    const matching = items.filter(
      (item) =>
        item.scope === scope &&
        item.status === status &&
        (category === 'all' || item.category === category),
    );
    const start = (pageNumber - 1) * pageSize;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Cache-Control': 'private, no-store' },
      body: JSON.stringify({
        items: matching.slice(start, start + pageSize),
        pagination: {
          page: pageNumber,
          pageSize,
          total: matching.length,
        },
      }),
    });
  });

  return requests;
}

async function openReview(
  page: Page,
  options: { empty?: boolean; fail?: boolean } = {},
) {
  const requests = await installReviewApi(page, options);
  await logIn(page);
  await page.goto(routes.review.path);
  return requests;
}

for (const viewport of [
  { key: 'mobile', width: 320, height: 900 },
  { key: 'desktop', width: 1440, height: 1000 },
] as const) {
  test(`shows the real Review queue without overflow at ${viewport.key} width`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const requests = await openReview(page);

    await expect(
      page.getByRole('heading', { level: 1, name: 'Review' }),
    ).toBeVisible();
    await expect(
      page.getByRole('radio', { name: 'Entry Insights' }),
    ).toBeChecked();
    await expect(page.getByText(entryItem.statement)).toBeVisible();
    await expect(page.getByRole('radio', { name: 'Ideas' })).toHaveCount(0);
    await expect(page.getByRole('searchbox')).toHaveCount(0);

    const dimensions = await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
    expect(
      requests.some(
        (request) =>
          request.method === 'GET' &&
          request.path.includes('scope=entry_insight') &&
          request.path.includes('page_size=1'),
      ),
    ).toBe(true);
    expect(
      requests.some(
        (request) =>
          request.method === 'GET' &&
          request.path.includes('scope=pattern') &&
          request.path.includes('page_size=1'),
      ),
    ).toBe(true);
  });
}

test('opens evidence and persists scope-correct feedback', async ({ page }) => {
  const requests = await openReview(page);
  await expect(page.getByText(entryItem.statement)).toBeVisible();

  const source = page.getByRole('button', {
    name: `View source evidence for: ${entryItem.statement}`,
  });
  await source.focus();
  await source.press('Enter');
  await expect(page.getByText(entryItem.sourceQuote ?? '')).toBeVisible();
  await page.getByRole('button', { name: 'Close' }).click();

  await page.getByRole('button', { name: 'Add correction or note' }).click();
  await page
    .getByRole('textbox', { name: 'Corrected statement' })
    .fill('Deadlines sometimes drain my energy.');
  await page
    .getByRole('textbox', { name: 'Note' })
    .fill('This depends on the project.');
  await page
    .getByRole('button', { name: `Partly accurate: ${entryItem.statement}` })
    .click();

  await expect
    .poll(() => requests.find((request) => request.method === 'POST')?.body)
    .toEqual({
      verdict: 'partly_accurate',
      correctedStatement: 'Deadlines sometimes drain my energy.',
      note: 'This depends on the project.',
    });

  await page.getByRole('radio', { name: 'Patterns' }).click();
  await expect(page.getByText(patternItem.statement)).toBeVisible();
  await page
    .getByRole('button', { name: `Resonates: ${patternItem.statement}` })
    .click();
  await expect
    .poll(
      () =>
        requests.filter((request) => request.method === 'POST').at(-1)?.body,
    )
    .toEqual({
      verdict: 'resonates',
      correctedStatement: null,
      note: null,
    });
});

test('renders empty and error recovery states', async ({ page }) => {
  await openReview(page, { empty: true });
  await expect(page.getByText('No Entry Insights need review')).toBeVisible();

  await page.unroute('**/api/v1/review/items**');
  await installReviewApi(page, { fail: true });
  await page.reload();
  await expect(page.getByText('Review is unavailable')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
});

test('redirects the legacy approvals bookmark to Review', async ({ page }) => {
  await installReviewApi(page);
  await logIn(page);
  await page.goto(routes.legacyApprovals.path);

  await expect(page).toHaveURL(routes.review.path);
  await expect(
    page.getByRole('heading', { level: 1, name: 'Review' }),
  ).toBeVisible();
});

import { expect, test, type Page } from '@playwright/test';

import type {
  ReviewFeedbackRequest,
  ReviewItem,
  ReviewStatus,
} from '../src/features/review';
import { routes } from '../src/config/routes';
import { logInWithSyntheticSession } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

function logIn(page: Page) {
  return logInWithSyntheticSession(page, {
    userId: '80000000-0000-4000-8000-000000000001',
    email: 'review-e2e@example.com',
    fullName: 'Review E2E',
    sessionId: 'review-e2e-session',
  });
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
  options: {
    empty?: boolean;
    fail?: boolean;
    waitForRelease?: Promise<void>;
  } = {},
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

    if (method === 'GET' && options.waitForRelease) {
      await options.waitForRelease;
    }

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
  options: Parameters<typeof installReviewApi>[1] = {},
) {
  const requests = await installReviewApi(page, options);
  await logIn(page);
  await page.goto(routes.review.path);
  return requests;
}

async function expectCenteredStateCard(
  page: Page,
  title: string,
  viewportWidth: number,
) {
  const heading = page.getByRole('heading', { name: title });
  const card = heading.locator('xpath=ancestor::*[@data-slot="card"]');
  const state = heading.locator(
    'xpath=ancestor::*[@role="status" or @role="alert"]',
  );

  await expect(heading).toBeVisible();
  await expect(card).toHaveCount(1);
  await expect(state).toHaveCSS('text-align', 'center');

  const cardBox = await card.boundingBox();
  const stateBox = await state.boundingBox();
  expect(cardBox).not.toBe(null);
  expect(stateBox).not.toBe(null);
  expect(cardBox!.width).toBeGreaterThanOrEqual(viewportWidth * 0.65);
  expect(
    Math.abs(
      cardBox!.x + cardBox!.width / 2 - (stateBox!.x + stateBox!.width / 2),
    ),
  ).toBeLessThanOrEqual(1);
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
    await expect(page.getByRole('combobox', { name: 'Category' })).toHaveCount(
      0,
    );
    await expect(page.getByRole('combobox', { name: 'Status' })).toHaveCount(0);
    const entryTag = page.getByText('Energy', { exact: true });
    await expect(entryTag).toBeVisible();
    await expect(entryTag).toHaveClass(/type-tag/);
    await expect(entryTag.locator('xpath=..')).toHaveClass(/float-right/);
    await expect(
      page
        .getByText(entryItem.statement)
        .locator('xpath=ancestor::*[@data-slot="card"]'),
    ).toHaveCount(1);

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
          request.path.includes('category=all') &&
          request.path.includes('status=pending') &&
          request.path.includes('page_size=1'),
      ),
    ).toBe(true);
    expect(
      requests.some(
        (request) =>
          request.method === 'GET' &&
          request.path.includes('scope=pattern') &&
          request.path.includes('category=all') &&
          request.path.includes('status=pending') &&
          request.path.includes('page_size=1'),
      ),
    ).toBe(true);
  });

  test(`centers Review loading and error cards at ${viewport.key} width`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    let releaseRequests!: () => void;
    const waitForRelease = new Promise<void>((resolve) => {
      releaseRequests = resolve;
    });

    await openReview(page, { waitForRelease });
    await expectCenteredStateCard(page, 'Loading', viewport.width);

    releaseRequests();
    await expect(page.getByText(entryItem.statement)).toBeVisible();

    await page.unroute('**/api/v1/review/items**');
    await installReviewApi(page, { fail: true });
    await page.reload();
    await expectCenteredStateCard(
      page,
      'Review is unavailable',
      viewport.width,
    );

    const dimensions = await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
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
  await expect(page.getByText('Hidden Driver', { exact: true })).toBeVisible();
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

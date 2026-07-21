import { expect, test, type Page } from '@playwright/test';

import type { ReflectionApiResponse } from '../src/features/reflections/api-schema';
import {
  reflectionApiFixture,
  reflectionFixtureIds,
} from '../src/features/reflections/fixtures';
import { routes } from '../src/config/routes';
import { logIn } from './helpers/auth';

test.describe.configure({ mode: 'serial' });

function updateFeedback(
  aggregate: ReflectionApiResponse,
  insightId: string,
  response: 'resonates' | 'partly' | 'rejected',
) {
  if (
    aggregate.data.hiddenDriver.status === 'available' &&
    aggregate.data.hiddenDriver.id === insightId
  ) {
    aggregate.data.hiddenDriver.feedback = response;
  }
  if (
    aggregate.data.recurringLoop.status === 'available' &&
    aggregate.data.recurringLoop.id === insightId
  ) {
    aggregate.data.recurringLoop.feedback = response;
  }
  if (aggregate.data.innerTensions.status === 'available') {
    const tension = aggregate.data.innerTensions.tensions.find(
      (item) => item.id === insightId,
    );
    if (tension) tension.feedback = response;
  }
}

async function installReflectionApi(
  page: Page,
  initial: ReflectionApiResponse = reflectionApiFixture,
) {
  const aggregate = structuredClone(initial);
  const requests: string[] = [];

  await page.route('**/api/v1/reflections**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push(`${request.method()} ${url.pathname}${url.search}`);

    if (request.method() === 'PUT') {
      const match = url.pathname.match(
        /\/reflections\/([^/]+)\/insights\/([^/]+)\/feedback$/,
      );
      const body = request.postDataJSON() as {
        response: 'resonates' | 'partly' | 'rejected';
      };
      if (!match) throw new Error('Unexpected feedback URL');
      updateFeedback(aggregate, match[2]!, body.response);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Cache-Control': 'private, no-store' },
        body: JSON.stringify({
          snapshotId: match[1],
          insightId: match[2],
          response: body.response,
          updatedAt: '2026-07-21T12:42:00Z',
        }),
      });
      return;
    }

    const range = url.searchParams.get('range');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Cache-Control': 'private, no-store' },
      body: JSON.stringify({ ...aggregate, range }),
    });
  });

  return requests;
}

async function openReflections(page: Page, response?: ReflectionApiResponse) {
  const requests = await installReflectionApi(page, response);
  await logIn(page);
  await page.goto(routes.reflections.path);
  return requests;
}

for (const viewport of [
  { key: 'mobile', width: 320, height: 900 },
  { key: 'tablet', width: 768, height: 1000 },
  { key: 'desktop', width: 1440, height: 1000 },
] as const) {
  test(`uses one aggregate request and has no page overflow at ${viewport.key} width`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const requests = await openReflections(page);
    await expect(page.getByText('Supported by 2 entries')).toBeVisible();
    await expect(
      page.getByRole('radio', { name: 'Latest 90 days' }),
    ).toBeChecked();

    for (const label of [
      'Hidden drivers',
      'Recurring loops',
      'Inner tensions',
    ]) {
      await page.getByRole('radio', { name: label }).click();
      await expect(
        page.getByRole('region', { name: `${label} reflection` }),
      ).toBeVisible();
      const dimensions = await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: document.documentElement.clientWidth,
      }));
      expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
    }

    expect(requests.filter((item) => item.startsWith('GET '))).toEqual([
      'GET /api/v1/reflections?range=all',
    ]);
    expect(requests[0]).not.toContain('userId');
    expect(requests[0]).not.toContain('reflectionTab');
  });
}

test('supports keyboard tabs and selected-insight evidence', async ({
  page,
}) => {
  await openReflections(page);
  await expect(page.getByText('Supported by 2 entries')).toBeVisible();

  const hiddenTab = page.getByRole('radio', { name: 'Hidden drivers' });
  await hiddenTab.focus();
  await hiddenTab.press('ArrowRight');
  const loopTab = page.getByRole('radio', { name: 'Recurring loops' });
  await expect(loopTab).toBeFocused();
  await loopTab.press('Space');
  await expect(
    page.getByRole('heading', { name: 'A loop that may be keeping you stuck' }),
  ).toBeVisible();

  await page.getByRole('radio', { name: 'Inner tensions' }).click();
  await page
    .getByRole('button', { name: 'View supporting entries' })
    .nth(1)
    .click();
  await expect(
    page.getByText(
      'Recognition restores me only when it comes from people and work I respect.',
    ),
  ).toBeVisible();
  await expect(
    page.getByText(
      'Explaining a difficult idea to someone else made the whole subject click for me.',
    ),
  ).toHaveCount(0);
});

test('persists feedback through the plural insight endpoint', async ({
  page,
}) => {
  const requests = await openReflections(page);
  await expect(page.getByText('Supported by 2 entries')).toBeVisible();

  const rejected = page.getByRole('button', { name: 'Not true for me' });
  await rejected.click();
  await expect(rejected).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.getByText(/will not treat this as an accepted self-pattern/),
  ).toBeVisible();
  await expect
    .poll(() => requests.filter((item) => item.startsWith('PUT ')))
    .toEqual([
      `PUT /api/v1/reflections/${reflectionFixtureIds.snapshot}/insights/${reflectionFixtureIds.hiddenDriver}/feedback`,
    ]);
});

test('renders first-pending and insufficient-content states from the API', async ({
  page,
}) => {
  const pending = structuredClone(reflectionApiFixture);
  pending.reflectionState = 'first_reflection_pending';
  pending.processingState = 'pending';
  pending.snapshot = null;
  pending.data.hiddenDriver = {
    status: 'insufficient_evidence',
    reasonCode: 'DRIVER_NOT_REPEATED',
    message: 'A hidden driver has not repeated enough yet.',
  };
  await openReflections(page, pending);
  await expect(
    page.getByText('Your first reflection is taking shape'),
  ).toBeVisible();
  await expect(
    page.getByRole('radio', { name: 'Hidden drivers' }),
  ).toBeVisible();

  const insufficient = structuredClone(reflectionApiFixture);
  insufficient.reflectionState = 'insufficient_reflective_content';
  insufficient.snapshot = null;
  insufficient.data.hiddenDriver = {
    status: 'insufficient_evidence',
    reasonCode: 'NOT_ENOUGH_REFLECTIVE_CONTENT',
    message: 'There is not enough personal reflection yet.',
  };
  await page.unroute('**/api/v1/reflections**');
  await installReflectionApi(page, insufficient);
  await page.reload();
  await expect(
    page.getByText('There is not enough personal reflection yet.'),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Write a new entry' }),
  ).toBeVisible();
});

test('shows no-results fallbacks for available insights without range evidence', async ({
  page,
}) => {
  const response = structuredClone(reflectionApiFixture);
  if (response.data.hiddenDriver.status === 'available') {
    response.data.hiddenDriver.evidence = [];
  }
  if (response.data.recurringLoop.status === 'available') {
    response.data.recurringLoop.evidence = [];
  }
  if (response.data.innerTensions.status === 'available') {
    response.data.innerTensions.tensions[0]!.evidence = [];
  }

  await openReflections(page, response);
  await expect(
    page.getByText('No supporting entries in this range'),
  ).toBeVisible();

  await page.getByRole('radio', { name: 'Recurring loops' }).click();
  await expect(
    page.getByText('No supporting entries in this range'),
  ).toBeVisible();

  await page.getByRole('radio', { name: 'Inner tensions' }).click();
  await expect(page.getByRole('heading', { name: 'Novelty' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Belonging' })).toBeVisible();
  await expect(page.getByText('Possible integration')).toHaveCount(1);
});

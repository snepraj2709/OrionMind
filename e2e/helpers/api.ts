import type { Page } from '@playwright/test';

export async function installPendingReviewCountApi(
  page: Page,
  counts: { entryInsights?: number; patterns?: number } = {},
) {
  const entryInsights = counts.entryInsights ?? 4;
  const patterns = counts.patterns ?? 2;

  await page.route('**/api/v1/review/items**', async (route) => {
    const url = new URL(route.request().url());
    const pageNumber = Number(url.searchParams.get('page') ?? '1');
    const pageSize = Number(url.searchParams.get('page_size') ?? '1');
    const total =
      url.searchParams.get('scope') === 'pattern' ? patterns : entryInsights;

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Cache-Control': 'private, no-store' },
      body: JSON.stringify({
        items: [],
        pagination: { page: pageNumber, pageSize, total },
      }),
    });
  });
}

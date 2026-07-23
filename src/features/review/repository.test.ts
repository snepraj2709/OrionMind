import { describe, expect, it, vi } from 'vitest';

import {
  HttpReviewRepository,
  ReviewRequestError,
  reviewRepository,
} from './repository';

const itemId = '81111111-1111-4111-8111-111111111111';
const entryId = '82222222-2222-4222-8222-222222222222';

function entryItem() {
  return {
    id: itemId,
    scope: 'entry_insight' as const,
    type: 'energy_loss' as const,
    category: 'energy' as const,
    statement: 'Preparing at the last minute drained your energy.',
    sourceQuote: 'The rushed preparation was exhausting.',
    sourceEntryIds: [entryId],
    sourceDates: ['2026-07-20'],
    inferenceLevel: 'direct' as const,
    confidence: 0.94,
    status: 'pending' as const,
    feedback: null,
  };
}

describe('reviewRepository', () => {
  it('uses the authorized HTTP implementation by default', () => {
    expect(reviewRepository).toBeInstanceOf(HttpReviewRepository);
  });
});

describe('HttpReviewRepository', () => {
  it('sends the exact snake_case list query and parses camelCase output', async () => {
    const body = {
      items: [entryItem()],
      pagination: { page: 2, pageSize: 20, total: 31 },
    };
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(body));
    const repository = new HttpReviewRepository(request);
    const controller = new AbortController();

    await expect(
      repository.listItems(
        {
          scope: 'entry_insight',
          category: 'energy',
          status: 'pending',
          page: 2,
          page_size: 20,
        },
        controller.signal,
      ),
    ).resolves.toEqual(body);

    const [path, init] = request.mock.calls[0] ?? [];
    const url = new URL(String(path), 'http://localhost');
    expect(url.pathname).toBe('/api/v1/review/items');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      scope: 'entry_insight',
      category: 'energy',
      status: 'pending',
      page: '2',
      page_size: '20',
    });
    expect(url.searchParams.has('userId')).toBe(false);
    expect(init).toEqual({ signal: controller.signal });
  });

  it('posts strict scope-specific feedback and parses the updated item', async () => {
    const updated = {
      ...entryItem(),
      status: 'partially_confirmed' as const,
      feedback: {
        verdict: 'partly_accurate' as const,
        correctedStatement: 'Deadlines sometimes drain my energy.',
        note: 'This depends on the project.',
        evidenceWeight: 0.5 as const,
        updatedAt: '2026-07-23T10:30:00Z',
      },
    };
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(updated));
    const repository = new HttpReviewRepository(request);

    await expect(
      repository.submitFeedback({
        itemId,
        scope: 'entry_insight',
        feedback: {
          verdict: 'partly_accurate',
          correctedStatement: ' Deadlines sometimes drain my energy. ',
          note: ' This depends on the project. ',
        },
      }),
    ).resolves.toEqual(updated);

    expect(request).toHaveBeenCalledWith(
      `/api/v1/review/items/${itemId}/feedback`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          verdict: 'partly_accurate',
          correctedStatement: 'Deadlines sometimes drain my energy.',
          note: 'This depends on the project.',
        }),
        signal: undefined,
      },
    );
  });

  it('rejects a cross-scope verdict before making a request', async () => {
    const request = vi.fn<typeof fetch>();
    const repository = new HttpReviewRepository(request);

    await expect(
      repository.submitFeedback({
        itemId,
        scope: 'pattern',
        feedback: {
          verdict: 'accurate',
          correctedStatement: null,
          note: null,
        },
      }),
    ).rejects.toThrow();
    expect(request).not.toHaveBeenCalled();
  });

  it('preserves request cancellation and reports HTTP failures safely', async () => {
    const controller = new AbortController();
    const request = vi.fn<typeof fetch>((_path, init) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        );
      });
    });
    const repository = new HttpReviewRepository(request);
    const pending = repository.listItems(
      {
        scope: 'pattern',
        category: 'all',
        status: 'pending',
        page: 1,
        page_size: 1,
      },
      controller.signal,
    );

    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });

    request.mockResolvedValueOnce(
      Response.json(
        {
          error_code: 'REFLECTION_RECALCULATION_UNAVAILABLE',
          message: 'Reflection recalculation is temporarily unavailable.',
        },
        { status: 503 },
      ),
    );
    await expect(
      repository.listItems({
        scope: 'pattern',
        category: 'all',
        status: 'pending',
        page: 1,
        page_size: 1,
      }),
    ).rejects.toEqual(
      new ReviewRequestError(
        'Review list request failed: 503',
        503,
        'REFLECTION_RECALCULATION_UNAVAILABLE',
      ),
    );
  });

  it('rejects malformed response casing instead of accepting a loose payload', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        items: [entryItem()],
        pagination: { page: 1, page_size: 20, total: 1 },
      }),
    );
    const repository = new HttpReviewRepository(request);

    await expect(
      repository.listItems({
        scope: 'entry_insight',
        category: 'all',
        status: 'pending',
        page: 1,
        page_size: 20,
      }),
    ).rejects.toThrow();
  });
});

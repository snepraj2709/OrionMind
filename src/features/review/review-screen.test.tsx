import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ReviewItem, ReviewListQuery, ReviewStatus } from './model';
import { reviewKeys } from './queries';
import {
  ReviewRequestError,
  type ReviewRepository,
  type SubmitReviewFeedbackInput,
} from './repository';
import { ReviewScreen } from './review-screen';

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    user: { id: '80000000-0000-4000-8000-000000000001' },
  }),
}));

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
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

function statusFor(input: SubmitReviewFeedbackInput): ReviewStatus {
  switch (input.feedback.verdict) {
    case 'accurate':
    case 'resonates':
      return 'confirmed';
    case 'partly_accurate':
    case 'partly_true':
      return 'partially_confirmed';
    case 'not_accurate':
    case 'not_true':
      return 'rejected';
  }
}

function weightFor(input: SubmitReviewFeedbackInput) {
  switch (statusFor(input)) {
    case 'confirmed':
      return 1 as const;
    case 'partially_confirmed':
      return 0.5 as const;
    case 'rejected':
      return 0 as const;
    case 'pending':
      throw new Error('Feedback cannot produce pending status.');
  }
}

function createRepository(initialItems: ReviewItem[]) {
  let items = structuredClone(initialItems);
  const listItems = vi.fn(async (query: ReviewListQuery) => {
    const matching = items.filter(
      (item) =>
        item.scope === query.scope &&
        item.status === query.status &&
        (query.category === 'all' || item.category === query.category),
    );
    const start = (query.page - 1) * query.page_size;
    return {
      items: matching.slice(start, start + query.page_size),
      pagination: {
        page: query.page,
        pageSize: query.page_size,
        total: matching.length,
      },
    };
  });
  const submitFeedback = vi.fn(
    async (input: SubmitReviewFeedbackInput): Promise<ReviewItem> => {
      const item = items.find((candidate) => candidate.id === input.itemId);
      if (!item) throw new Error('Missing item');
      const status = statusFor(input);
      const feedback = {
        ...input.feedback,
        evidenceWeight: weightFor(input),
        correctedStatement: input.feedback.correctedStatement?.trim() || null,
        note: input.feedback.note?.trim() || null,
        updatedAt: '2026-07-23T10:30:00Z',
      };
      const updated = { ...item, status, feedback } as ReviewItem;
      items = items.map((candidate) =>
        candidate.id === updated.id ? updated : candidate,
      );
      return updated;
    },
  );

  return { listItems, submitFeedback } satisfies ReviewRepository;
}

function renderReview(repository: ReviewRepository) {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  return {
    queryClient,
    ...render(<ReviewScreen repository={repository} />, { wrapper: Wrapper }),
  };
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'onLine');
});

describe('ReviewScreen', () => {
  it('renders the real two-scope IA and editorial loading state', () => {
    renderReview({
      listItems: () => new Promise(() => undefined),
      submitFeedback: vi.fn(),
    });

    expect(
      screen.getByRole('heading', { level: 1, name: 'Review' }),
    ).toBeVisible();
    expect(
      screen.getByText(
        'Confirm, refine, or reject the insights Orion may use in your reflections.',
      ),
    ).toBeVisible();
    expect(screen.getByRole('radio', { name: 'Entry Insights' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Patterns' })).toBeVisible();
    expect(
      screen.queryByRole('radio', { name: 'Ideas' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('radio', { name: 'Memories' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('combobox', { name: 'Theme' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('combobox', { name: 'Category' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('combobox', { name: 'Status' }),
    ).not.toBeInTheDocument();
    const loadingHeading = screen.getByRole('heading', { name: 'Loading' });
    expect(loadingHeading.closest('[data-slot="card"]')).toBeInTheDocument();
  });

  it('switches scopes and requests every pending category from page one', async () => {
    const repository = createRepository([entryItem, patternItem]);
    const user = userEvent.setup();
    renderReview(repository);

    expect(await screen.findByText(entryItem.statement)).toBeVisible();
    expect(repository.listItems).toHaveBeenLastCalledWith(
      {
        scope: 'entry_insight',
        category: 'all',
        status: 'pending',
        page: 1,
        page_size: 20,
      },
      expect.any(AbortSignal),
    );
    for (const label of ['Accurate', 'Partly accurate', 'Not accurate']) {
      expect(
        screen.getByRole('button', {
          name: `${label}: ${entryItem.statement}`,
        }),
      ).toBeVisible();
    }

    await user.click(screen.getByRole('radio', { name: 'Patterns' }));
    expect(await screen.findByText(patternItem.statement)).toBeVisible();
    for (const label of ['Resonates', 'Partly true', 'Not true']) {
      expect(
        screen.getByRole('button', {
          name: `${label}: ${patternItem.statement}`,
        }),
      ).toBeVisible();
    }
    expect(repository.listItems).toHaveBeenLastCalledWith(
      {
        scope: 'pattern',
        category: 'all',
        status: 'pending',
        page: 1,
        page_size: 20,
      },
      expect.any(AbortSignal),
    );
  });

  it('renders tagged cards and opens exact source evidence by keyboard', async () => {
    const user = userEvent.setup();
    renderReview(createRepository([entryItem]));

    const statement = await screen.findByText(entryItem.statement);
    expect(statement).toHaveClass('type-journal-excerpt');
    expect(statement.closest('li')?.querySelector('hr')).toBe(null);
    expect(
      statement.closest('li')?.querySelector('[data-slot="card"]'),
    ).toHaveClass('radius-card', 'border', 'border-border', 'bg-card');
    const categoryTag = screen.getByText('Energy');
    expect(categoryTag).toHaveClass(
      'type-tag',
      'border-accent/40',
      'bg-accent/10',
    );
    expect(categoryTag.parentElement).toHaveClass(
      'float-right',
      'mb-2',
      'ml-4',
    );

    const sourceButton = screen.getByRole('button', {
      name: `View source evidence for: ${entryItem.statement}`,
    });
    sourceButton.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByText(entryItem.sourceQuote ?? '')).toBeVisible();
  });

  it('represents Pattern entry IDs and distinct dates without inventing index alignment', async () => {
    const user = userEvent.setup();
    const item = {
      ...patternItem,
      sourceEntryIds: [
        ...patternItem.sourceEntryIds,
        '86666666-6666-4666-8666-666666666666',
      ],
    } satisfies ReviewItem;
    renderReview(createRepository([item]));

    await user.click(screen.getByRole('radio', { name: 'Patterns' }));
    await screen.findByText(item.statement);
    const sourceButton = screen.getByRole('button', {
      name: `View source evidence for: ${item.statement}`,
    });
    expect(sourceButton).toHaveTextContent('View 2 evidence dates');
    await user.click(sourceButton);

    expect(screen.getByText('Evidence context')).toBeVisible();
    expect(
      screen.getByText(
        'One or more journal entries on this date contributed validated evidence to this pattern.',
      ),
    ).toHaveClass('type-body');
    expect(
      screen.getByText(
        '3 journal entries across 2 dates contributed validated evidence. Full journal text remains in Entries.',
      ),
    ).toBeVisible();
    expect(screen.getByText('1 of 2')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('2 of 2')).toBeVisible();
  });

  it('uses fixed pagination and requests the selected one-based page', async () => {
    const items = Array.from({ length: 21 }, (_, index) => ({
      ...entryItem,
      id: `81111111-1111-4111-8111-${String(index + 1).padStart(12, '0')}`,
      statement: `Review statement ${index + 1}`,
    })) satisfies ReviewItem[];
    const repository = createRepository(items);
    const user = userEvent.setup();
    renderReview(repository);

    expect(await screen.findAllByText(/Review statement/)).toHaveLength(20);
    expect(screen.getByText('Page 1 of 2')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText('Review statement 21')).toBeVisible();
    expect(repository.listItems).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2, page_size: 20 }),
      expect.any(AbortSignal),
    );
  });

  it('submits exact Entry correction/note and Pattern verdict bodies', async () => {
    const repository = createRepository([entryItem, patternItem]);
    const user = userEvent.setup();
    renderReview(repository);

    await screen.findByText(entryItem.statement);
    await user.click(
      screen.getByRole('button', { name: 'Add correction or note' }),
    );
    await user.type(
      screen.getByRole('textbox', { name: 'Corrected statement' }),
      'Deadlines sometimes drain my energy.',
    );
    await user.type(
      screen.getByRole('textbox', { name: 'Note' }),
      'This depends on the project.',
    );
    await user.click(
      screen.getByRole('button', {
        name: `Partly accurate: ${entryItem.statement}`,
      }),
    );

    await waitFor(() =>
      expect(repository.submitFeedback).toHaveBeenCalledWith({
        itemId: entryItem.id,
        scope: 'entry_insight',
        feedback: {
          verdict: 'partly_accurate',
          correctedStatement: 'Deadlines sometimes drain my energy.',
          note: 'This depends on the project.',
        },
      }),
    );
    expect(
      await screen.findByText(/corrected statement saved/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Patterns' }));
    await screen.findByText(patternItem.statement);
    await user.click(
      screen.getByRole('button', {
        name: `Resonates: ${patternItem.statement}`,
      }),
    );
    await waitFor(() =>
      expect(repository.submitFeedback).toHaveBeenLastCalledWith({
        itemId: patternItem.id,
        scope: 'pattern',
        feedback: {
          verdict: 'resonates',
          correctedStatement: '',
          note: '',
        },
      }),
    );
  });

  it('renders the pending queue empty state without filter recovery controls', async () => {
    renderReview(createRepository([]));

    expect(
      await screen.findByText('No Entry Insights need review'),
    ).toBeVisible();
    expect(
      screen.queryByRole('button', { name: 'Clear filters' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('No matching results')).not.toBeInTheDocument();
  });

  it('recovers from initial and mutation errors with retry actions', async () => {
    const user = userEvent.setup();
    const repository = createRepository([entryItem]);
    repository.listItems
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockImplementation(createRepository([entryItem]).listItems);
    repository.submitFeedback
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockImplementation(createRepository([entryItem]).submitFeedback);
    renderReview(repository);

    expect(await screen.findByText('Review is unavailable')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await screen.findByText(entryItem.statement);
    await user.click(
      screen.getByRole('button', {
        name: `Accurate: ${entryItem.statement}`,
      }),
    );
    expect(
      await screen.findByText(
        /could not confirm whether your feedback was saved/i,
      ),
    ).toBeVisible();
    await user.click(
      screen.getByRole('button', {
        name: `Retry feedback for: ${entryItem.statement}`,
      }),
    );
    await waitFor(() =>
      expect(repository.submitFeedback).toHaveBeenCalledTimes(2),
    );
  });

  it('refreshes durable feedback after recalculation scheduling returns 503', async () => {
    const user = userEvent.setup();
    let item: ReviewItem = entryItem;
    const repository = createRepository([entryItem]);
    repository.listItems.mockImplementation(async (query) => {
      const items =
        item.scope === query.scope && item.status === query.status
          ? [item]
          : [];
      return {
        items,
        pagination: {
          page: query.page,
          pageSize: query.page_size,
          total: items.length,
        },
      };
    });
    repository.submitFeedback.mockImplementation(async () => {
      item = {
        ...entryItem,
        status: 'confirmed',
        feedback: {
          verdict: 'accurate',
          evidenceWeight: 1,
          correctedStatement: null,
          note: null,
          updatedAt: '2026-07-23T10:30:00Z',
        },
      };
      throw new ReviewRequestError(
        `Review feedback request failed: 503`,
        503,
        'REFLECTION_RECALCULATION_UNAVAILABLE',
      );
    });
    renderReview(repository);

    await screen.findByText(entryItem.statement);
    await user.click(
      screen.getByRole('button', {
        name: `Accurate: ${entryItem.statement}`,
      }),
    );

    expect(
      await screen.findByText(
        /feedback was saved, but Reflection recalculation/i,
      ),
    ).toBeVisible();
    expect(
      screen.queryByText(/Review item is unchanged/i),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByText('No Entry Insights need review'),
    ).toBeVisible();
    expect(repository.listItems).toHaveBeenCalledTimes(2);
    expect(
      screen.queryByRole('button', { name: 'Retry' }),
    ).not.toBeInTheDocument();
  });

  it('keeps stale rows visible but disables every action while refetching', async () => {
    let resolveRefresh:
      | ((value: Awaited<ReturnType<ReviewRepository['listItems']>>) => void)
      | undefined;
    const repository = createRepository([entryItem]);
    repository.listItems
      .mockResolvedValueOnce({
        items: [entryItem],
        pagination: { page: 1, pageSize: 20, total: 1 },
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve;
          }),
      );
    const { queryClient } = renderReview(repository);

    await screen.findByText(entryItem.statement);
    void queryClient.invalidateQueries({
      queryKey: reviewKeys.user('80000000-0000-4000-8000-000000000001'),
    });
    expect(
      await screen.findByRole('heading', { name: 'Refreshing' }),
    ).toBeVisible();
    expect(screen.getByText(entryItem.statement)).toBeVisible();
    expect(
      screen.getByRole('button', {
        name: `Accurate: ${entryItem.statement}`,
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('radio', { name: 'Entry Insights' }),
    ).toBeDisabled();

    await act(async () =>
      resolveRefresh?.({
        items: [entryItem],
        pagination: { page: 1, pageSize: 20, total: 1 },
      }),
    );
  });

  it('keeps stale rows non-actionable after a background refresh fails', async () => {
    const repository = createRepository([entryItem]);
    repository.listItems
      .mockResolvedValueOnce({
        items: [entryItem],
        pagination: { page: 1, pageSize: 20, total: 1 },
      })
      .mockRejectedValueOnce(new Error('Unavailable'));
    const { queryClient } = renderReview(repository);

    await screen.findByText(entryItem.statement);
    void queryClient.invalidateQueries({
      queryKey: reviewKeys.user('80000000-0000-4000-8000-000000000001'),
    });

    expect(
      await screen.findByText(/queue could not be refreshed/i),
    ).toBeVisible();
    expect(
      screen.getByRole('heading', { name: 'Refresh failed' }),
    ).toBeVisible();
    expect(screen.getByText(entryItem.statement)).toBeVisible();
    expect(
      screen.getByRole('button', {
        name: `Accurate: ${entryItem.statement}`,
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('radio', { name: 'Entry Insights' }),
    ).toBeDisabled();
  });

  it('returns to the last valid page when refreshed data shrinks', async () => {
    const items = Array.from({ length: 21 }, (_, index) => ({
      ...entryItem,
      id: `81111111-1111-4111-8111-${String(index + 1).padStart(12, '0')}`,
      statement: `Review statement ${index + 1}`,
    })) satisfies ReviewItem[];
    let total = items.length;
    const repository = createRepository(items);
    repository.listItems.mockImplementation(async (query) => {
      const matching = items.slice(0, total);
      const start = (query.page - 1) * query.page_size;
      return {
        items: matching.slice(start, start + query.page_size),
        pagination: {
          page: query.page,
          pageSize: query.page_size,
          total: matching.length,
        },
      };
    });
    const user = userEvent.setup();
    const { queryClient } = renderReview(repository);

    await screen.findAllByText(/Review statement/);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText('Review statement 21')).toBeVisible();

    total = 20;
    void queryClient.invalidateQueries({
      queryKey: reviewKeys.user('80000000-0000-4000-8000-000000000001'),
    });

    expect(await screen.findByText('Review statement 1')).toBeVisible();
    expect(repository.listItems).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1 }),
      expect.any(AbortSignal),
    );
  });

  it('keeps loaded rows readable but disables feedback while offline', async () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    });
    renderReview(createRepository([entryItem]));

    expect(await screen.findByText(/You are offline/)).toBeVisible();
    expect(await screen.findByText(entryItem.statement)).toBeVisible();
    expect(
      screen.getByRole('button', {
        name: `Accurate: ${entryItem.statement}`,
      }),
    ).toBeDisabled();
  });
});

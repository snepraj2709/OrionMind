import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { ReviewRepository } from './repository';
import { ReviewAwareNavigation, ReviewQueueSummary } from './review-navigation';

vi.mock('next/navigation', () => ({
  usePathname: () => '/review',
}));

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    user: { id: '80000000-0000-4000-8000-000000000001' },
  }),
}));

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })
      }
    >
      {children}
    </QueryClientProvider>
  );
}

describe('Review navigation', () => {
  it('sums real pending totals from both Review scopes', async () => {
    const repository: ReviewRepository = {
      listItems: vi.fn(async (query) => ({
        items: [],
        pagination: {
          page: 1,
          pageSize: 1,
          total: query.scope === 'entry_insight' ? 3 : 2,
        },
      })),
      submitFeedback: vi.fn(),
    };

    render(
      <>
        <ReviewAwareNavigation repository={repository} />
        <ReviewQueueSummary repository={repository} />
      </>,
      { wrapper: Wrapper },
    );

    expect(await screen.findAllByLabelText('5 items to review')).toHaveLength(
      2,
    );
    expect(repository.listItems).toHaveBeenCalledTimes(2);
    expect(repository.listItems).toHaveBeenCalledWith(
      {
        scope: 'entry_insight',
        category: 'all',
        status: 'pending',
        page: 1,
        page_size: 1,
      },
      expect.any(AbortSignal),
    );
    expect(repository.listItems).toHaveBeenCalledWith(
      {
        scope: 'pattern',
        category: 'all',
        status: 'pending',
        page: 1,
        page_size: 1,
      },
      expect.any(AbortSignal),
    );
  });

  it('does not present a failed pending-count query as zero', async () => {
    const repository: ReviewRepository = {
      listItems: vi.fn().mockRejectedValue(new Error('Unavailable')),
      submitFeedback: vi.fn(),
    };

    render(
      <>
        <ReviewAwareNavigation repository={repository} />
        <ReviewQueueSummary repository={repository} />
      </>,
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(repository.listItems).toHaveBeenCalledTimes(2));
    const summary = screen.getByLabelText('Review queue');
    expect(summary).toBeVisible();
    expect(summary.querySelector('[aria-hidden="true"]')).toBeNull();
    expect(screen.queryByLabelText(/items to review/i)).not.toBeInTheDocument();
    expect(screen.queryByText('0 to review')).not.toBeInTheDocument();
  });
});

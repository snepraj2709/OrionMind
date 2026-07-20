import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApprovalsScreen } from './approvals-screen';
import { MockApprovalsRepository } from './mock-repository';
import type { ApprovalRecord, ApprovalsResult } from './model';
import type { ApprovalsRepository } from './repository';

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

const idea: ApprovalRecord = {
  id: 'idea-1',
  content: 'I want to protect slow mornings.',
  entryDate: '2025-07-10',
  entryId: 'entry-1',
  kind: 'idea',
  status: 'pending_approval',
  themes: ['health'],
};

const memory: ApprovalRecord = {
  ...idea,
  id: 'memory-1',
  content: 'I found language for my own authority.',
  kind: 'memory',
  themes: ['career'],
};

const reflection: ApprovalRecord = {
  ...idea,
  id: 'reflection-1',
  content: 'Quiet gives me room to notice what I need.',
  kind: 'reflection',
  themes: ['personalGrowth'],
};

function renderApprovals(repository: ApprovalsRepository) {
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
    ...render(<ApprovalsScreen repository={repository} />, {
      wrapper: Wrapper,
    }),
  };
}

function result(
  items: ApprovalRecord[],
  totalAll = items.length,
): ApprovalsResult {
  return { items, total: items.length, totalAll };
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'onLine');
});

describe('ApprovalsScreen', () => {
  it('shows the approved header, defaults, and editorial loading shape', () => {
    renderApprovals({
      decideApproval: vi.fn(),
      listPendingApprovals: () => new Promise(() => undefined),
    });

    expect(
      screen.getByText(
        'Approve or dismiss what Orion extracted from your entries.',
      ),
    ).toBeVisible();
    expect(screen.getByRole('radio', { name: 'Ideas' })).toBeChecked();
    expect(screen.getByRole('combobox', { name: 'Status' })).toHaveTextContent(
      'All Status',
    );
    expect(screen.getByRole('combobox', { name: 'Theme' })).toHaveTextContent(
      'All Themes',
    );
    expect(screen.getByRole('status', { name: 'Loading items' })).toBeVisible();
  });

  it('switches immediately between Ideas, Memories, and Reflections', async () => {
    const user = userEvent.setup();
    renderApprovals(new MockApprovalsRepository([idea, memory, reflection], 0));

    expect(await screen.findByText(idea.content)).toBeVisible();
    expect(screen.queryByText(memory.content)).not.toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Memories' }));
    expect(await screen.findByText(memory.content)).toBeVisible();
    expect(screen.queryByText(idea.content)).not.toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Reflections' }));
    expect(await screen.findByText(reflection.content)).toBeVisible();
    expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  });

  it('submits search explicitly while theme filtering remains immediate', async () => {
    const user = userEvent.setup();
    renderApprovals(
      new MockApprovalsRepository(
        [
          idea,
          {
            ...idea,
            id: 'idea-2',
            content: 'A career experiment.',
            themes: ['career'],
          },
        ],
        0,
      ),
    );

    await screen.findByText(idea.content);
    const searchbox = screen.getByRole('searchbox', {
      name: 'Search review queue',
    });
    await user.type(searchbox, 'career');
    expect(screen.getByText(idea.content)).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByText('A career experiment.')).toBeVisible();
    expect(screen.queryByText(idea.content)).not.toBeInTheDocument();

    await user.clear(
      screen.getByRole('searchbox', { name: 'Search review queue' }),
    );
    await user.keyboard('{Enter}');
    await user.click(screen.getByRole('combobox', { name: 'Theme' }));
    await user.click(screen.getByRole('option', { name: 'Health' }));
    expect(await screen.findByText(idea.content)).toBeVisible();
    expect(screen.queryByText('A career experiment.')).not.toBeInTheDocument();
  });

  it('renders minimal rows with editorial action styles and separators', async () => {
    renderApprovals(new MockApprovalsRepository([idea], 0));

    const statement = await screen.findByText(idea.content);
    expect(statement).toHaveClass('type-journal-excerpt');
    const row = statement.closest('li');
    expect(row?.querySelector('hr')).toHaveClass('border-border');
    expect(row?.querySelector('[data-slot="surface"]')).toBeNull();
    expect(screen.getByRole('button', { name: 'Approve' })).toHaveClass(
      'border-accent',
      'text-accent',
    );
    expect(screen.getByRole('button', { name: 'Reject' })).toHaveClass(
      'border-border',
      'text-muted-foreground',
      'hover:border-destructive',
      'hover:text-destructive',
    );
  });

  it('uses a fixed five-item page and clamps after a decision', async () => {
    const items = Array.from({ length: 6 }, (_, index) => ({
      ...idea,
      id: `idea-${index + 1}`,
      content: `Idea statement ${index + 1}`,
    }));
    const user = userEvent.setup();
    renderApprovals(new MockApprovalsRepository(items, 0));

    expect(await screen.findAllByText(/Idea statement/)).toHaveLength(5);
    expect(screen.getByText('Page 1 of 2')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText('Idea statement 6')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText('Page 1 of 1')).toBeVisible();
    expect(screen.getByText('Idea statement 1')).toBeVisible();
  });

  it('decides an item and removes it from the pending queue', async () => {
    const repository = new MockApprovalsRepository([idea], 0);
    const decideApproval = vi.spyOn(repository, 'decideApproval');
    const user = userEvent.setup();
    renderApprovals(repository);

    await screen.findByText(idea.content);
    await user.click(screen.getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('You are all caught up')).toBeVisible();
    expect(decideApproval).toHaveBeenCalledWith({
      id: idea.id,
      status: 'approved',
    });
  });

  it('marks Reflections stale without immediately refetching after approval', async () => {
    const repository = new MockApprovalsRepository([reflection], 0);
    const user = userEvent.setup();
    const { queryClient } = renderApprovals(repository);
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries');

    await user.click(screen.getByRole('radio', { name: 'Reflections' }));
    await screen.findByText(reflection.content);
    await user.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() =>
      expect(invalidateQueries).toHaveBeenCalledWith({
        queryKey: ['reflections'],
        refetchType: 'none',
      }),
    );
  });

  it('distinguishes an empty queue from filtered-empty results', async () => {
    const user = userEvent.setup();
    renderApprovals(new MockApprovalsRepository([idea], 0));
    await screen.findByText(idea.content);

    await user.type(
      screen.getByRole('searchbox', { name: 'Search review queue' }),
      'missing',
    );
    expect(screen.queryByText('No matching results')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByText('No matching results')).toBeVisible();
    expect(screen.queryByText('You are all caught up')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(await screen.findByText(idea.content)).toBeVisible();

    renderApprovals(new MockApprovalsRepository([], 0));
    expect(await screen.findByText('You are all caught up')).toBeVisible();
  });

  it('keeps queue items visible during a background refresh', async () => {
    let resolveRefresh: ((value: ApprovalsResult) => void) | undefined;
    const listPendingApprovals = vi
      .fn<ApprovalsRepository['listPendingApprovals']>()
      .mockResolvedValueOnce(result([idea]))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve;
          }),
      );
    const { queryClient } = renderApprovals({
      decideApproval: vi.fn(),
      listPendingApprovals,
    });

    await screen.findByText(idea.content);
    void queryClient.invalidateQueries({ queryKey: ['approvals'] });

    expect(await screen.findByText('Refreshing review queue…')).toBeVisible();
    expect(screen.getByText(idea.content)).toBeVisible();
    await act(async () => resolveRefresh?.(result([idea])));
  });

  it('shows a recovery action when the queue fails', async () => {
    const listPendingApprovals = vi
      .fn<ApprovalsRepository['listPendingApprovals']>()
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce(result([idea]));
    const repository: ApprovalsRepository = {
      decideApproval: vi.fn(),
      listPendingApprovals,
    };
    const user = userEvent.setup();

    renderApprovals(repository);

    expect(await screen.findByText('Review is unavailable')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(idea.content)).toBeVisible();
    expect(listPendingApprovals).toHaveBeenCalledTimes(2);
  });

  it('keeps the queue readable but disables decisions while offline', async () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    });
    renderApprovals(new MockApprovalsRepository([idea], 0));

    expect(await screen.findByText(/You are offline/)).toBeVisible();
    expect(await screen.findByText(idea.content)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  });

  it('sends complete typed filters to the repository', async () => {
    const listPendingApprovals = vi
      .fn<ApprovalsRepository['listPendingApprovals']>()
      .mockResolvedValue(result([idea]));
    renderApprovals({ decideApproval: vi.fn(), listPendingApprovals });

    await waitFor(() =>
      expect(listPendingApprovals).toHaveBeenCalledWith({
        kind: 'idea',
        pageIndex: 0,
        pageSize: 5,
        search: '',
        status: 'all',
        theme: 'all',
      }),
    );
  });
});

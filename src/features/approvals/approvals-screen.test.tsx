import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
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
};

const memory: ApprovalRecord = {
  ...idea,
  id: 'memory-1',
  content: 'I found language for my own authority.',
  kind: 'memory',
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

  return render(<ApprovalsScreen repository={repository} />, {
    wrapper: Wrapper,
  });
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
  it('shows an editorial loading shape before the queue arrives', () => {
    renderApprovals({
      decideApproval: vi.fn(),
      listPendingApprovals: () => new Promise(() => undefined),
    });

    expect(screen.getByRole('status', { name: 'Loading items' })).toBeVisible();
  });

  it('filters the review queue by item kind', async () => {
    const user = userEvent.setup();
    renderApprovals(new MockApprovalsRepository([idea, memory], 0));

    expect(await screen.findByText(idea.content)).toBeVisible();
    expect(screen.getByText(memory.content)).toBeVisible();

    screen.getByRole('combobox', { name: 'Show' }).focus();
    await user.keyboard('{Enter}{ArrowDown}{ArrowDown}{Enter}');

    expect(await screen.findByText(memory.content)).toBeVisible();
    expect(screen.queryByText(idea.content)).not.toBeInTheDocument();
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

  it('distinguishes an empty queue from filtered-empty results', async () => {
    const user = userEvent.setup();
    renderApprovals(new MockApprovalsRepository([idea], 0));
    await screen.findByText(idea.content);

    await user.type(
      screen.getByRole('searchbox', { name: 'Search review queue' }),
      'missing',
    );
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
    const user = userEvent.setup();
    renderApprovals({ decideApproval: vi.fn(), listPendingApprovals });

    await screen.findByText(idea.content);
    await user.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(
      screen.getByRole('button', { name: 'Refreshing review queue' }),
    ).toBeDisabled();
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
});

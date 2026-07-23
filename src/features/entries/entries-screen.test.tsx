import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { EntriesListRepository } from './repository';
import { EntriesScreen } from './entries-screen';
import type { EntriesResult, EntrySummary } from './model';
import { entryKeys } from './query-keys';

const completedEntry: EntrySummary = {
  id: 'entry-1',
  content: 'A quiet morning made the rest of the day feel more spacious.',
  date: '2025-07-10',
  inputType: 'text',
  status: 'completed',
  themes: ['personalGrowth'],
};

function result(items: EntrySummary[], total = items.length): EntriesResult {
  return {
    items,
    total,
    page: 1,
    pageSize: 10,
  };
}

function repositoryWithList(
  listEntries: EntriesListRepository['listEntries'],
): EntriesListRepository {
  return { listEntries };
}

function renderEntries(
  repository: EntriesListRepository,
  pendingReviewCount?: number | null,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <EntriesScreen
        pendingReviewCount={pendingReviewCount}
        repository={repository}
      />
    </QueryClientProvider>,
  );
}

describe('EntriesScreen', () => {
  it('shows the initial editorial loading state', () => {
    const repository = repositoryWithList(() => new Promise(() => undefined));

    renderEntries(repository);

    const loadingHeading = screen.getByRole('heading', { name: 'Loading' });
    expect(loadingHeading.closest('[data-slot="card"]')).toBeInTheDocument();
    expect(screen.getByText('Loading review count')).toBeVisible();
  });

  it('renders successful, queued, processing, and failed entries', async () => {
    const repository = repositoryWithList(
      vi.fn().mockResolvedValue(
        result([
          completedEntry,
          { ...completedEntry, id: 'entry-pending', status: 'pending' },
          {
            ...completedEntry,
            id: 'entry-2',
            inputType: 'voice',
            status: 'processing',
          },
          { ...completedEntry, id: 'entry-3', status: 'failed' },
        ]),
      ),
    );

    renderEntries(repository);

    expect(await screen.findAllByText(completedEntry.content)).toHaveLength(4);
    expect(
      screen.getByText('Queued', { selector: '[data-slot="badge"]' }),
    ).toBeVisible();
    expect(
      screen.getByText('Processing', { selector: '[data-slot="badge"]' }),
    ).toBeVisible();
    expect(
      screen.getByText('Processing failed', {
        selector: '[data-slot="badge"]',
      }),
    ).toBeVisible();
    expect(screen.getAllByRole('link', { name: /10 Jul/ })).toHaveLength(4);
    expect(screen.getByText('Voice')).toBeVisible();
    expect(screen.getAllByText('Personal Growth')).toHaveLength(4);
    expect(screen.getAllByText(completedEntry.content)[0]).toHaveClass(
      'line-clamp-2',
    );
    expect(
      screen.queryByText('Complete', { selector: '[data-slot="badge"]' }),
    ).not.toBeInTheDocument();
  });

  it('shows dynamic entry and review totals with the fixed pagination size', async () => {
    const listEntries = vi
      .fn<EntriesListRepository['listEntries']>()
      .mockResolvedValue(result([completedEntry]));

    renderEntries(repositoryWithList(listEntries), 3);

    expect(
      await screen.findByLabelText('1 entry, 3 awaiting review'),
    ).toBeVisible();
    expect(listEntries).toHaveBeenCalledWith(
      expect.objectContaining({ pageSize: 10 }),
    );
    expect(
      screen.queryByRole('combobox', { name: 'Rows per page' }),
    ).not.toBeInTheDocument();
  });

  it('does not present an unavailable Review count as zero', async () => {
    renderEntries(
      repositoryWithList(vi.fn().mockResolvedValue(result([completedEntry]))),
      null,
    );

    expect(
      await screen.findByLabelText('1 entry, Review count unavailable'),
    ).toBeVisible();
    expect(screen.queryByText('0 awaiting review')).not.toBeInTheDocument();
  });

  it('does not show unsupported search or status filters', async () => {
    renderEntries(
      repositoryWithList(vi.fn().mockResolvedValue(result([completedEntry]))),
    );

    await screen.findByText(completedEntry.content);
    expect(
      screen.queryByRole('searchbox', { name: 'Search entries' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('combobox', { name: 'Status' }),
    ).not.toBeInTheDocument();
  });

  it('renders an empty journal with a direct action', async () => {
    const repository = repositoryWithList(
      vi.fn().mockResolvedValue(result([])),
    );

    renderEntries(repository);

    expect(await screen.findByText('Your journal is ready')).toBeVisible();
    expect(
      screen.getByRole('link', { name: 'Add your first entry' }),
    ).toHaveAttribute('href', '/entries/new');
  });

  it('keeps API pagination aligned and requests each selected page once', async () => {
    const secondPageEntry = {
      ...completedEntry,
      id: 'entry-11',
      content: 'The final entry on the second page.',
    };
    const listEntries = vi.fn<EntriesListRepository['listEntries']>(
      async (query) => ({
        items: query.pageIndex === 0 ? [completedEntry] : [secondPageEntry],
        page: query.pageIndex + 1,
        pageSize: 10,
        total: 11,
      }),
    );
    const user = userEvent.setup();

    renderEntries(repositoryWithList(listEntries));
    expect(await screen.findByText('Page 1 of 2')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Next' }));

    expect(await screen.findByText(secondPageEntry.content)).toBeVisible();
    expect(screen.getByText('Page 2 of 2')).toBeVisible();
    expect(listEntries).toHaveBeenCalledTimes(2);
    expect(listEntries).toHaveBeenLastCalledWith(
      expect.objectContaining({ pageIndex: 1, pageSize: 10 }),
    );
  });

  it('clamps back to the last valid page when a response page is empty', async () => {
    let secondPageRequested = false;
    const listEntries = vi.fn<EntriesListRepository['listEntries']>(
      async (query) => {
        if (query.pageIndex === 1) {
          secondPageRequested = true;
          return {
            items: [],
            page: 2,
            pageSize: 10,
            total: 5,
          };
        }

        return {
          items: [completedEntry],
          page: 1,
          pageSize: 10,
          total: secondPageRequested ? 5 : 11,
        };
      },
    );
    const user = userEvent.setup();

    renderEntries(repositoryWithList(listEntries));
    expect(await screen.findByText('Page 1 of 2')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() =>
      expect(listEntries).toHaveBeenLastCalledWith(
        expect.objectContaining({ pageIndex: 0 }),
      ),
    );
    expect(await screen.findByText('Page 1 of 1')).toBeVisible();
    expect(listEntries).toHaveBeenCalledTimes(3);
  });

  it('shows an error and retries through the repository boundary', async () => {
    const listEntries = vi
      .fn<EntriesListRepository['listEntries']>()
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce(result([completedEntry]));
    const user = userEvent.setup();

    renderEntries(repositoryWithList(listEntries));

    expect(await screen.findByText('Entries are unavailable')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText(completedEntry.content)).toBeVisible();
    expect(listEntries).toHaveBeenCalledTimes(2);
  });

  it('keeps existing content visible during a background refresh', async () => {
    let resolveRefresh: ((value: EntriesResult) => void) | undefined;
    const listEntries = vi
      .fn<EntriesListRepository['listEntries']>()
      .mockResolvedValueOnce(result([completedEntry]))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve;
          }),
      );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <EntriesScreen repository={repositoryWithList(listEntries)} />
      </QueryClientProvider>,
    );
    await screen.findByText(completedEntry.content);
    void queryClient.invalidateQueries({ queryKey: entryKeys.lists });

    expect(
      await screen.findByRole('heading', { name: 'Refreshing' }),
    ).toBeVisible();
    expect(screen.getByText(completedEntry.content)).toBeVisible();

    resolveRefresh?.(result([completedEntry]));
  });
});

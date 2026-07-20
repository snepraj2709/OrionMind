import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { EntriesRepository } from './repository';
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

function result(items: EntrySummary[], totalAll = items.length): EntriesResult {
  return { items, total: items.length, totalAll };
}

function repositoryWithList(
  listEntries: EntriesRepository['listEntries'],
): EntriesRepository {
  return {
    listEntries,
    getEntry: vi.fn(),
    createTextEntry: vi.fn(),
    createVoiceEntry: vi.fn(),
    decideExtractedItem: vi.fn(),
    retryEntry: vi.fn(),
  };
}

function renderEntries(repository: EntriesRepository, pendingReviewCount = 0) {
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

    expect(screen.getByRole('status', { name: 'Loading items' })).toBeVisible();
  });

  it('renders successful, processing, and failed entries', async () => {
    const repository = repositoryWithList(
      vi.fn().mockResolvedValue(
        result([
          completedEntry,
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

    expect(await screen.findAllByText(completedEntry.content)).toHaveLength(3);
    expect(
      screen.getByText('Processing', { selector: '[data-slot="badge"]' }),
    ).toBeVisible();
    expect(
      screen.getByText('Processing failed', {
        selector: '[data-slot="badge"]',
      }),
    ).toBeVisible();
    expect(screen.getAllByRole('link', { name: /10 Jul/ })).toHaveLength(3);
    expect(screen.getByText('Voice')).toBeVisible();
    expect(screen.getAllByText('Personal Growth')).toHaveLength(3);
    expect(screen.getAllByText(completedEntry.content)[0]).toHaveClass(
      'line-clamp-2',
    );
    expect(
      screen.queryByText('Complete', { selector: '[data-slot="badge"]' }),
    ).not.toBeInTheDocument();
  });

  it('shows dynamic entry and review totals with the fixed pagination size', async () => {
    const listEntries = vi
      .fn<EntriesRepository['listEntries']>()
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

  it('keeps status filtering and resets the query to the first page', async () => {
    const processingEntry = {
      ...completedEntry,
      id: 'entry-processing',
      status: 'processing' as const,
    };
    const listEntries = vi.fn<EntriesRepository['listEntries']>(
      async (query) =>
        query.status === 'processing'
          ? result([processingEntry], 2)
          : result([completedEntry, processingEntry], 2),
    );
    const user = userEvent.setup();

    renderEntries(repositoryWithList(listEntries));
    await screen.findByLabelText('2 entries, 0 awaiting review');
    await user.click(screen.getByRole('combobox', { name: 'Status' }));
    await user.click(screen.getByRole('option', { name: 'Processing' }));

    await waitFor(() =>
      expect(listEntries).toHaveBeenLastCalledWith(
        expect.objectContaining({ pageIndex: 0, status: 'processing' }),
      ),
    );
    expect(
      screen.getByText('Processing', { selector: '[data-slot="badge"]' }),
    ).toBeVisible();
    expect(screen.getAllByRole('link', { name: /10 Jul/ })).toHaveLength(1);
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

  it('distinguishes filtered-empty results from an empty journal', async () => {
    const repository = repositoryWithList(
      vi.fn(async (query) =>
        query.search ? result([], 1) : result([completedEntry]),
      ),
    );
    const user = userEvent.setup();

    renderEntries(repository);
    await screen.findByText(completedEntry.content);
    await user.type(
      screen.getByRole('searchbox', { name: 'Search entries' }),
      'missing',
    );
    expect(screen.queryByText('No matching results')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByText('No matching results')).toBeVisible();
    expect(screen.queryByText('Your journal is ready')).not.toBeInTheDocument();
  });

  it('shows an error and retries through the repository boundary', async () => {
    const listEntries = vi
      .fn<EntriesRepository['listEntries']>()
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
      .fn<EntriesRepository['listEntries']>()
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

    expect(await screen.findByText('Refreshing entries…')).toBeVisible();
    expect(screen.getByText(completedEntry.content)).toBeVisible();

    resolveRefresh?.(result([completedEntry]));
  });
});

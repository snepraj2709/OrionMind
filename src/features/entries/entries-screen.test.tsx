import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { EntriesRepository } from './repository';
import { EntriesScreen } from './entries-screen';
import type { EntriesResult, EntrySummary } from './model';

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

function renderEntries(repository: EntriesRepository) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <EntriesScreen repository={repository} />
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
      vi
        .fn()
        .mockResolvedValue(
          result([
            completedEntry,
            { ...completedEntry, id: 'entry-2', status: 'processing' },
            { ...completedEntry, id: 'entry-3', status: 'failed' },
          ]),
        ),
    );

    renderEntries(repository);

    expect(await screen.findByText('Complete')).toBeVisible();
    expect(screen.getByText('Processing')).toBeVisible();
    expect(screen.getByText('Processing failed')).toBeVisible();
    expect(screen.getAllByRole('link', { name: /July 10, 2025/ })).toHaveLength(
      3,
    );
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
    await screen.findByText('Complete');
    await user.type(
      screen.getByRole('searchbox', { name: 'Search entries' }),
      'missing',
    );

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

    expect(await screen.findByText('Complete')).toBeVisible();
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
    const user = userEvent.setup();

    renderEntries(repositoryWithList(listEntries));
    await screen.findByText('Complete');
    await user.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(screen.getByText('Refreshing entries…')).toBeVisible();
    expect(screen.getByText(completedEntry.content)).toBeVisible();

    resolveRefresh?.(result([completedEntry]));
  });
});

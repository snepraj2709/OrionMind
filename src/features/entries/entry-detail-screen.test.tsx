import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EntryDetail } from './model';
import type { EntriesRepository } from './repository';
import { EntryDetailScreen } from './entry-detail-screen';

const completedEntry: EntryDetail = {
  id: 'e1',
  content:
    'This morning I sat with my coffee longer than usual and watched the light change.',
  date: '2025-07-10',
  inputType: 'text',
  status: 'completed',
  themes: ['personalGrowth', 'health'],
  ideas: [
    {
      id: 'i1',
      content: 'Protect slow, screen-free time in the morning.',
      kind: 'idea',
      status: 'pending_approval',
    },
  ],
  memories: [
    {
      id: 'm1',
      content: 'Stillness made the rest of the day feel more spacious.',
      kind: 'memory',
      status: 'approved',
    },
  ],
};

function createRepository(
  overrides: Partial<EntriesRepository> = {},
): EntriesRepository {
  return {
    createTextEntry: vi.fn(),
    createVoiceEntry: vi.fn(),
    decideExtractedItem: vi.fn().mockResolvedValue(completedEntry),
    getEntry: vi.fn().mockResolvedValue(completedEntry),
    listEntries: vi.fn().mockResolvedValue({
      items: [],
      total: 0,
      totalAll: 0,
    }),
    retryEntry: vi
      .fn()
      .mockResolvedValue({ ...completedEntry, status: 'processing' }),
    ...overrides,
  };
}

function renderEntryDetail(repository = createRepository()) {
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

  return render(<EntryDetailScreen entryId="e1" repository={repository} />, {
    wrapper: Wrapper,
  });
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'onLine');
});

describe('EntryDetailScreen', () => {
  it('shows an editorial loading shape before the entry arrives', () => {
    renderEntryDetail(
      createRepository({
        getEntry: () => new Promise(() => undefined),
      }),
    );

    expect(screen.getByRole('status', { name: 'Loading items' })).toBeVisible();
  });

  it('renders a completed entry and saves an approval decision', async () => {
    const approvedEntry: EntryDetail = {
      ...completedEntry,
      ideas: [{ ...completedEntry.ideas[0], status: 'approved' }],
    };
    const decideExtractedItem = vi.fn().mockResolvedValue(approvedEntry);
    const repository = createRepository({ decideExtractedItem });
    const user = userEvent.setup();
    renderEntryDetail(repository);

    expect(
      await screen.findByRole('heading', { name: 'July 10, 2025' }),
    ).toBeVisible();
    expect(screen.getByText('Personal Growth')).toBeVisible();
    expect(screen.getByText('Health')).toBeVisible();

    const ideaCard = screen
      .getByText('Protect slow, screen-free time in the morning.')
      .closest('[data-slot="card"]');
    expect(ideaCard).not.toBeNull();
    await user.click(
      within(ideaCard as HTMLElement).getByRole('button', {
        name: 'Approve',
      }),
    );

    await waitFor(() =>
      expect(decideExtractedItem).toHaveBeenCalledWith({
        entryId: 'e1',
        itemId: 'i1',
        kind: 'idea',
        status: 'approved',
      }),
    );
    expect(
      await within(ideaCard as HTMLElement).findByText('Approved'),
    ).toBeVisible();
  });

  it('keeps the original entry visible while reflection is processing', async () => {
    renderEntryDetail(
      createRepository({
        getEntry: vi
          .fn()
          .mockResolvedValue({ ...completedEntry, status: 'processing' }),
      }),
    );

    expect(
      await screen.findByText('Orion is reflecting on this entry'),
    ).toBeVisible();
    expect(screen.getByText(completedEntry.content)).toBeVisible();
  });

  it('retries failed reflection without hiding the original entry', async () => {
    const failedEntry: EntryDetail = {
      ...completedEntry,
      status: 'failed',
      processingError: 'Reflection was interrupted.',
    };
    const retryEntry = vi
      .fn()
      .mockResolvedValue({ ...failedEntry, status: 'processing' });
    const user = userEvent.setup();
    renderEntryDetail(
      createRepository({
        getEntry: vi.fn().mockResolvedValue(failedEntry),
        retryEntry,
      }),
    );

    expect(await screen.findByText('Reflection did not finish')).toBeVisible();
    expect(screen.getByText(completedEntry.content)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry reflection' }));

    expect(
      await screen.findByText('Orion is reflecting on this entry'),
    ).toBeVisible();
    expect(retryEntry).toHaveBeenCalledWith('e1');
  });

  it('distinguishes a missing entry from a loading error', async () => {
    renderEntryDetail(
      createRepository({ getEntry: vi.fn().mockResolvedValue(null) }),
    );

    expect(await screen.findByText('Entry not found')).toBeVisible();
    expect(
      screen.getByRole('link', { name: 'Return to entries' }),
    ).toHaveAttribute('href', '/entries');
  });

  it('shows a load error and retries through the repository boundary', async () => {
    const getEntry = vi
      .fn<EntriesRepository['getEntry']>()
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce(completedEntry);
    const user = userEvent.setup();
    renderEntryDetail(createRepository({ getEntry }));

    expect(await screen.findByText('Entry unavailable')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(
      await screen.findByRole('heading', { name: 'July 10, 2025' }),
    ).toBeVisible();
    expect(getEntry).toHaveBeenCalledTimes(2);
  });

  it('keeps loaded content visible during a background refresh', async () => {
    let resolveRefresh: ((entry: EntryDetail) => void) | undefined;
    const getEntry = vi
      .fn<EntriesRepository['getEntry']>()
      .mockResolvedValueOnce(completedEntry)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve;
          }),
      );
    const user = userEvent.setup();
    renderEntryDetail(createRepository({ getEntry }));

    await screen.findByText(completedEntry.content);
    await user.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(screen.getByText('Refreshing entry…')).toBeVisible();
    expect(screen.getByText(completedEntry.content)).toBeVisible();
    await act(async () => resolveRefresh?.(completedEntry));
  });

  it('keeps data readable but disables decisions while offline', async () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    });
    renderEntryDetail();

    expect(await screen.findByText(/You are offline/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByText(completedEntry.content)).toBeVisible();
  });
});

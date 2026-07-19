import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  MockReflectionsRepository,
  reflectionEntryFixtures,
} from './mock-repository';
import { ReflectionsScreen } from './reflections-screen';
import type { JournalEntry, ReflectionEntriesResult } from './model';
import type { ReflectionsRepository } from './repository';

function result(
  entries: JournalEntry[],
  totalAvailable = entries.length,
): ReflectionEntriesResult {
  return { entries, totalAvailable };
}

function renderReflections(repository: ReflectionsRepository) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  return render(<ReflectionsScreen repository={repository} />, {
    wrapper: Wrapper,
  });
}

describe('ReflectionsScreen', () => {
  it('shows an editorial loading state while entries are gathered', () => {
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 50),
    );

    expect(screen.getByRole('status', { name: 'Loading items' })).toBeVisible();
  });

  it('renders the connected story and reveals original evidence on demand', async () => {
    const user = userEvent.setup();
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );

    expect(
      await screen.findByText(/Patterns taking shape across 23 entries/),
    ).toBeVisible();
    expect(
      screen.getByRole('heading', { name: 'Hidden drivers' }),
    ).toBeVisible();
    expect(
      screen.getByText('A loop that may be keeping you stuck'),
    ).toBeVisible();
    expect(
      screen.getByText('Needs you may be trying to hold at the same time'),
    ).toBeVisible();

    await user.click(
      screen.getByRole('button', { name: 'View supporting entries' }),
    );
    expect(
      await screen.findByRole('heading', { name: 'Supporting entries' }),
    ).toBeVisible();
    expect(screen.getByText('Your journal')).toBeVisible();
  });

  it('softens a user-rejected insight and confirms the trust behavior', async () => {
    const user = userEvent.setup();
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );

    await screen.findByText('What seems to drive you');
    await user.click(screen.getByRole('button', { name: 'Not true for me' }));

    expect(
      screen.getByText(/will not treat this as an accepted self-pattern/),
    ).toBeVisible();
  });

  it('distinguishes no history from insufficient history', async () => {
    const { unmount } = renderReflections(new MockReflectionsRepository([], 0));
    expect(
      await screen.findByText('Your reflection history is ready to begin'),
    ).toBeVisible();
    unmount();

    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures.slice(0, 3), 0),
    );
    expect(
      await screen.findByText('A little more history is needed'),
    ).toBeVisible();
  });

  it('distinguishes a date-range miss from an empty journal', async () => {
    const repository: ReflectionsRepository = {
      getReflectionEntries: vi.fn().mockResolvedValue(result([], 23)),
    };
    renderReflections(repository);

    expect(
      await screen.findByText('No entries in this date range'),
    ).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Show all entries' }),
    ).toBeVisible();
  });

  it('retries an initial load failure', async () => {
    const getReflectionEntries = vi
      .fn<ReflectionsRepository['getReflectionEntries']>()
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce(result(reflectionEntryFixtures));
    const repository: ReflectionsRepository = {
      getReflectionEntries,
    };
    const user = userEvent.setup();
    renderReflections(repository);

    expect(
      await screen.findByText('Reflections are unavailable'),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(
      await screen.findByText(/Patterns taking shape across 23 entries/),
    ).toBeVisible();
  });

  it('preserves the current view when a background refresh fails', async () => {
    let rejectRefresh: ((reason?: unknown) => void) | undefined;
    const getReflectionEntries = vi
      .fn<ReflectionsRepository['getReflectionEntries']>()
      .mockResolvedValueOnce(result(reflectionEntryFixtures))
      .mockImplementationOnce(
        () =>
          new Promise<ReflectionEntriesResult>((_resolve, reject) => {
            rejectRefresh = reject;
          }),
      );
    const user = userEvent.setup();
    renderReflections({ getReflectionEntries });

    expect(
      await screen.findByText(/Patterns taking shape across 23 entries/),
    ).toBeVisible();
    await user.click(
      screen.getByRole('button', { name: 'Refresh reflections' }),
    );
    expect(
      screen.getByRole('status', { name: /Refreshing reflections/ }),
    ).toBeVisible();

    rejectRefresh?.(new Error('Refresh unavailable'));

    expect(
      await screen.findByText(/Showing the last available view/),
    ).toBeVisible();
    expect(screen.getByText('What seems to drive you')).toBeVisible();
  });
});

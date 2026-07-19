import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  MockReflectionsRepository,
  reflectionEntryFixtures,
} from './mock-repository';
import type { JournalEntry, ReflectionEntriesResult } from './model';
import { ReflectionsScreen } from './reflections-screen';
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

  it('defaults to All entries and the exact eight-entry Hidden Drivers view', async () => {
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );

    expect(
      await screen.findByText(
        'Patterns taking shape across 8 entries from 14 Apr–8 May.',
      ),
    ).toBeVisible();
    expect(screen.getByRole('radio', { name: 'All entries' })).toHaveAttribute(
      'data-state',
      'on',
    );
    expect(
      screen.getByText(/You appear most energised when curiosity becomes/),
    ).toBeVisible();
    expect(screen.getByText('Observed across 8 entries')).toBeVisible();
    expect(screen.getAllByRole('region', { name: /reflection$/ })).toHaveLength(
      1,
    );
    expect(
      screen.getByRole('radio', { name: 'Hidden drivers' }),
    ).toHaveAttribute('aria-checked', 'true');
  });

  it('switches one visible panel at a time and supports arrow-key navigation', async () => {
    const user = userEvent.setup();
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );
    await screen.findByText('Observed across 8 entries');

    const hiddenDrivers = screen.getByRole('radio', {
      name: 'Hidden drivers',
    });
    hiddenDrivers.focus();
    await user.keyboard('{ArrowRight}{Enter}');

    expect(
      screen.getByRole('heading', {
        name: 'A loop that may be keeping you stuck',
      }),
    ).toBeVisible();
    expect(screen.getAllByRole('region', { name: /reflection$/ })).toHaveLength(
      1,
    );
    expect(
      screen.queryByText('Observed across 8 entries'),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getByTestId('inner-tensions-tab-icon')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {
        name: 'Needs you may be trying to hold at the same time',
      }),
    ).toBeVisible();
    expect(screen.getAllByRole('region', { name: /reflection$/ })).toHaveLength(
      1,
    );
  });

  it('renders all six loop steps with their exact entry counts', async () => {
    const user = userEvent.setup();
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );
    await screen.findByText('Observed across 8 entries');
    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));

    const list = screen.getByRole('list');
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(6);
    expect(within(list).getAllByRole('separator')).toHaveLength(5);
    [4, 5, 6, 3, 4, 5].forEach((count, index) => {
      expect(rows[index]).toHaveTextContent(`${count} entries`);
    });
    expect(
      screen.getByText(
        'The excitement of possibility without requiring you to risk choosing one direction.',
      ),
    ).toBeVisible();
  });

  it('renders exactly two tension cards with the screenshot copy', async () => {
    const user = userEvent.setup();
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );
    await screen.findByText('Observed across 8 entries');
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));

    expect(
      screen.getByRole('heading', { name: 'Novelty and exploration' }),
    ).toBeVisible();
    expect(
      screen.getByRole('heading', { name: 'Focus and completion' }),
    ).toBeVisible();
    expect(
      screen.getByRole('heading', { name: 'Recognition and belonging' }),
    ).toBeVisible();
    expect(
      screen.getByRole('heading', { name: 'Autonomy and distinctiveness' }),
    ).toBeVisible();
    expect(screen.getAllByText('Possible integration')).toHaveLength(2);
  });

  it('records shared pill feedback and confirms rejection', async () => {
    const user = userEvent.setup();
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );
    await screen.findByText('Observed across 8 entries');

    const rejected = screen.getByRole('button', { name: 'Not true for me' });
    await user.click(rejected);

    expect(rejected).toHaveAttribute('aria-pressed', 'true');
    expect(rejected).toHaveClass('radius-pill');
    expect(
      screen.getByText(/will not treat this as an accepted self-pattern/),
    ).toBeVisible();
  });

  it('opens contextual evidence from the page header', async () => {
    const user = userEvent.setup();
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );
    await screen.findByText('Observed across 8 entries');

    await user.click(
      screen.getByRole('button', { name: 'Why am I seeing this?' }),
    );
    expect(
      await screen.findByRole('heading', { name: 'Supporting entries' }),
    ).toBeVisible();
    expect(screen.getByText('Your journal')).toBeVisible();
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
      getReflectionEntries: vi.fn().mockResolvedValue(result([], 8)),
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
    const user = userEvent.setup();
    renderReflections({ getReflectionEntries });

    expect(
      await screen.findByText('Reflections are unavailable'),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(
      await screen.findByText(/Patterns taking shape across 8 entries/),
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
      await screen.findByText(/Patterns taking shape across 8 entries/),
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
    expect(screen.getByText('Observed across 8 entries')).toBeVisible();
  });

  it('keeps cached data visible while offline', async () => {
    const originalOnline = navigator.onLine;
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    });

    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures, 0),
    );
    window.dispatchEvent(new Event('offline'));

    expect(
      await screen.findByText(
        /Orion is showing the last available reflections/,
      ),
    ).toBeVisible();
    expect(screen.getByText('Observed across 8 entries')).toBeVisible();

    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: originalOnline,
    });
    window.dispatchEvent(new Event('online'));
  });
});

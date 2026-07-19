import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { PropsWithChildren } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { journeyEntryFixtures, MockJourneyRepository } from './mock-repository';
import { JourneyScreen } from './journey-screen';
import type { JourneyEntriesResult } from './model';
import type { JourneyRepository } from './repository';

function renderScreen(repository: JourneyRepository) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }
  return render(<JourneyScreen repository={repository} />, {
    wrapper: Wrapper,
  });
}

describe('JourneyScreen', () => {
  it('shows a calm loading state while the longitudinal view is assembled', () => {
    renderScreen(new MockJourneyRepository(journeyEntryFixtures, 50));

    expect(
      screen.getByRole('status', { name: 'Loading items' }),
    ).toBeInTheDocument();
  });

  it('shows the theme river, chapters, and chapter analysis', async () => {
    const user = userEvent.setup();
    renderScreen(new MockJourneyRepository(journeyEntryFixtures, 0));
    expect(
      await screen.findByRole('heading', { name: 'Life Theme River' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /chapters detected/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('tab', { name: 'Chapter DNA' }),
    ).toBeInTheDocument();
    await user.click(screen.getByText('View data table'));
    expect(
      screen.getByRole('table', { name: 'Relative theme presence by period' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Transformation Arc' }));
    expect(
      await screen.findByRole('heading', { name: 'Transformation arc' }),
    ).toBeInTheDocument();
  });

  it('opens supporting evidence from an interpretation', async () => {
    const user = userEvent.setup();
    renderScreen(new MockJourneyRepository(journeyEntryFixtures, 0));
    await screen.findByRole('heading', { name: 'Life Theme River' });
    await user.click(
      screen.getAllByRole('button', { name: 'Why am I seeing this?' })[0]!,
    );
    expect(
      screen.getByRole('heading', { name: 'Supporting entries' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Your journal')).toBeInTheDocument();
  });

  it('shows the insufficient-history state', async () => {
    renderScreen(
      new MockJourneyRepository(journeyEntryFixtures.slice(0, 3), 0),
    );
    expect(
      await screen.findByRole('heading', {
        name: 'A little more history is needed',
      }),
    ).toBeInTheDocument();
  });

  it('distinguishes an empty journal from a limited date range', async () => {
    renderScreen(new MockJourneyRepository([], 0));
    expect(
      await screen.findByRole('heading', {
        name: 'Your journey is ready to begin',
      }),
    ).toBeInTheDocument();
  });

  it('distinguishes an empty date range from an empty journal', async () => {
    renderScreen({
      getJourneyEntries: vi.fn().mockResolvedValue({
        entries: [],
        totalAvailable: 8,
      }),
    });
    expect(
      await screen.findByRole('heading', {
        name: 'No entries in this date range',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Show all entries' }),
    ).toBeInTheDocument();
  });

  it('shows separate insufficient-theme and no-chapter states', async () => {
    const entriesWithoutThemes = journeyEntryFixtures
      .slice(0, 6)
      .map((entry) => ({
        ...entry,
        theme: [],
      }));
    renderScreen(new MockJourneyRepository(entriesWithoutThemes, 0));

    expect(
      await screen.findByRole('heading', {
        name: 'Not enough theme data for the river',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'No chapters detected yet' }),
    ).toBeInTheDocument();
  });

  it('renames a detected chapter without changing routes', async () => {
    const user = userEvent.setup();
    renderScreen(new MockJourneyRepository(journeyEntryFixtures, 0));
    await screen.findByRole('heading', { name: 'Life Theme River' });

    await user.click(screen.getByRole('button', { name: 'Edit chapter name' }));
    await user.clear(screen.getByRole('textbox', { name: 'Chapter name' }));
    await user.type(
      screen.getByRole('textbox', { name: 'Chapter name' }),
      'Learning to choose deliberately',
    );
    await user.click(screen.getByRole('button', { name: 'Save name' }));

    expect(
      screen.getByRole('heading', {
        name: 'Learning to choose deliberately',
        level: 2,
      }),
    ).toBeInTheDocument();
  });

  it('selects a boundary and explains it without technical scores', async () => {
    const user = userEvent.setup();
    renderScreen(new MockJourneyRepository(journeyEntryFixtures, 0));
    await screen.findByRole('heading', { name: 'Life Theme River' });

    await user.click(
      screen.getAllByRole('button', { name: /Chapter boundary on/ })[0]!,
    );
    expect(
      screen.getByRole('heading', {
        name: 'Why Orion detected a new chapter',
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/similarity|confidence/i),
    ).not.toBeInTheDocument();
  });

  it('preserves the current journey when a background refresh fails', async () => {
    let rejectRefresh: ((reason?: unknown) => void) | undefined;
    const initialResult: JourneyEntriesResult = {
      entries: journeyEntryFixtures,
      totalAvailable: journeyEntryFixtures.length,
    };
    const getJourneyEntries = vi
      .fn<JourneyRepository['getJourneyEntries']>()
      .mockResolvedValueOnce(initialResult)
      .mockImplementationOnce(
        () =>
          new Promise<JourneyEntriesResult>((_resolve, reject) => {
            rejectRefresh = reject;
          }),
      );
    const user = userEvent.setup();
    renderScreen({ getJourneyEntries });
    await screen.findByRole('heading', { name: 'Life Theme River' });

    await user.click(screen.getByRole('button', { name: 'Refresh journey' }));
    expect(
      screen.getByRole('status', { name: 'Refreshing journey' }),
    ).toBeInTheDocument();
    rejectRefresh?.(new Error('Refresh unavailable'));

    expect(
      await screen.findByText(/Showing the last available view/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Life Theme River' }),
    ).toBeInTheDocument();
  });

  it('retries after a repository error', async () => {
    const getJourneyEntries = vi
      .fn<JourneyRepository['getJourneyEntries']>()
      .mockRejectedValueOnce(new Error('nope'))
      .mockResolvedValueOnce({
        entries: journeyEntryFixtures,
        totalAvailable: journeyEntryFixtures.length,
      });
    const user = userEvent.setup();
    renderScreen({ getJourneyEntries });
    expect(
      await screen.findByRole('heading', {
        name: 'Your journey is unavailable',
      }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(getJourneyEntries).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByRole('heading', { name: 'Life Theme River' }),
    ).toBeInTheDocument();
  });
});

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { PropsWithChildren } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { journeyEntryFixtures, journeyStreamForRange } from './fixtures';
import { JourneyScreen } from './journey-screen';
import { MockJourneyRepository } from './mock-repository';
import type { JourneyResponse, JourneyStatusResponse } from './model';
import type { JourneyRepository } from './repository';

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ user: { id: 'reader-id' } }),
}));

const unlockedStatus: JourneyStatusResponse = {
  enabled: true,
  daysSinceSignup: 90,
  entriesAdded: 30,
};

function response(
  entries = journeyEntryFixtures,
  range: JourneyResponse['range'] = 'all',
): JourneyResponse {
  return {
    entries,
    range,
    stream: journeyStreamForRange(range),
    totalAvailable: entries.length,
  };
}

function unlockedRepository(entries = journeyEntryFixtures, delay = 0) {
  return new MockJourneyRepository(entries, delay, unlockedStatus);
}

function renderScreen(repository?: JourneyRepository) {
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
  it('shows the same fixed locked Journey by default', async () => {
    renderScreen();

    expect(
      await screen.findByRole('heading', { name: 'Not enough data yet' }),
    ).toBeVisible();
    expect(
      screen.getByRole('progressbar', {
        name: 'Days since signup: 18 of 30, 60%',
      }),
    ).toBeVisible();
    expect(
      screen.getByRole('progressbar', {
        name: 'Entries added: 9 of 15, 60%',
      }),
    ).toBeVisible();
    expect(
      screen.getByRole('img', {
        name: 'Locked preview of your personal journey',
      }),
    ).toBeVisible();
    expect(
      screen.getByRole('img', {
        name: 'Sample unlocked journey theme streamgraph',
      }),
    ).toBeVisible();
    expect(screen.getByText('Sample')).toBeVisible();
    expect(screen.getByRole('radio', { name: 'All' })).toBeChecked();
    expect(
      screen.queryByRole('button', { name: 'Refresh journey' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Life Theme River' }),
    ).not.toBeInTheDocument();
  });

  it('shows a calm loading state while the longitudinal view is assembled', () => {
    renderScreen(unlockedRepository(journeyEntryFixtures, 50));

    const loadingHeading = screen.getByRole('heading', { name: 'Loading' });
    expect(loadingHeading.closest('[data-slot="card"]')).toBeInTheDocument();
  });

  it('shows the theme river, chapters, and chapter analysis when enabled', async () => {
    const user = userEvent.setup();
    renderScreen(unlockedRepository());
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

  it('renders the exact locked hierarchy and submits range changes with the user id', async () => {
    const getJourney = vi
      .fn<JourneyRepository['getJourney']>()
      .mockResolvedValue(response());
    const repository: JourneyRepository = {
      getJourney,
      getJourneyStatus: vi.fn().mockResolvedValue({
        enabled: false,
        daysSinceSignup: 18,
        entriesAdded: 9,
      }),
    };
    const user = userEvent.setup();
    renderScreen(repository);

    expect(
      await screen.findByRole('heading', { name: 'Not enough data yet' }),
    ).toBeVisible();
    expect(
      screen.getByText(
        'Journey unlocks after 30 days of signup with at least 15 entries across those 30 days.',
      ),
    ).toBeVisible();
    expect(
      screen.getByRole('progressbar', {
        name: 'Days since signup: 18 of 30, 60%',
      }),
    ).toBeVisible();
    expect(
      screen.getByRole('progressbar', {
        name: 'Entries added: 9 of 15, 60%',
      }),
    ).toBeVisible();
    expect(
      screen.getByRole('img', {
        name: 'Sample unlocked journey theme streamgraph',
      }),
    ).toBeVisible();
    expect(screen.getByRole('radio', { name: 'All' })).toBeChecked();

    await user.click(screen.getByRole('radio', { name: '6M' }));
    await waitFor(() =>
      expect(getJourney).toHaveBeenLastCalledWith('6m', 'reader-id'),
    );
  });

  it('opens supporting evidence from an interpretation', async () => {
    const user = userEvent.setup();
    renderScreen(unlockedRepository());
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
    renderScreen(unlockedRepository(journeyEntryFixtures.slice(0, 3)));
    expect(
      await screen.findByRole('heading', {
        name: 'A little more history is needed',
      }),
    ).toBeInTheDocument();
  });

  it('distinguishes an empty journal from a limited date range', async () => {
    renderScreen(unlockedRepository([]));
    expect(
      await screen.findByRole('heading', {
        name: 'Your journey is ready to begin',
      }),
    ).toBeInTheDocument();
  });

  it('distinguishes an empty date range from an empty journal', async () => {
    renderScreen({
      getJourney: vi.fn().mockResolvedValue({
        ...response([]),
        totalAvailable: 8,
      }),
      getJourneyStatus: vi.fn().mockResolvedValue(unlockedStatus),
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
      .map((entry) => ({ ...entry, theme: [] }));
    renderScreen(unlockedRepository(entriesWithoutThemes));

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
    renderScreen(unlockedRepository());
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
    renderScreen(unlockedRepository());
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
    const getJourney = vi
      .fn<JourneyRepository['getJourney']>()
      .mockResolvedValueOnce(response())
      .mockImplementationOnce(
        () =>
          new Promise<JourneyResponse>((_resolve, reject) => {
            rejectRefresh = reject;
          }),
      );
    const user = userEvent.setup();
    renderScreen({
      getJourney,
      getJourneyStatus: vi.fn().mockResolvedValue(unlockedStatus),
    });
    await screen.findByRole('heading', { name: 'Life Theme River' });

    await user.click(screen.getByRole('button', { name: 'Refresh journey' }));
    expect(
      screen.getByRole('heading', { name: 'Refreshing' }),
    ).toBeInTheDocument();
    rejectRefresh?.(new Error('Refresh unavailable'));

    expect(
      await screen.findByText(/Showing the last available view/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Life Theme River' }),
    ).toBeInTheDocument();
  });

  it('retries both requests after a repository error', async () => {
    const getJourney = vi
      .fn<JourneyRepository['getJourney']>()
      .mockRejectedValueOnce(new Error('nope'))
      .mockResolvedValueOnce(response());
    const getJourneyStatus = vi
      .fn<JourneyRepository['getJourneyStatus']>()
      .mockResolvedValue(unlockedStatus);
    const user = userEvent.setup();
    renderScreen({ getJourney, getJourneyStatus });
    expect(
      await screen.findByRole('heading', {
        name: 'Your journey is unavailable',
      }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(getJourney).toHaveBeenCalledTimes(2));
    expect(getJourneyStatus).toHaveBeenCalledTimes(2);
    expect(
      await screen.findByRole('heading', { name: 'Life Theme River' }),
    ).toBeInTheDocument();
  });
});

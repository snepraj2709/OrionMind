import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  MockReflectionsRepository,
  reflectionEntryFixtures,
} from './mock-repository';
import type { ReflectionApiResponse, ReflectionRequest } from './api-schema';
import type { JournalEntry } from './model';
import { ReflectionsScreen } from './reflections-screen';
import type { ReflectionsRepository } from './repository';
import { buildReflectionApiResponse } from './response-builder';

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ user: { id: 'reader-id' } }),
}));

function result(
  entries: JournalEntry[],
  totalAvailable = entries.length,
  input: ReflectionRequest = {
    userId: 'reader-id',
    reflectionTab: 'hiddenDriver',
    range: 'all',
  },
): ReflectionApiResponse {
  return buildReflectionApiResponse({
    ...input,
    entries,
    totalAvailable,
  });
}

function emptyArrayResult(input: ReflectionRequest): ReflectionApiResponse {
  const response = result(reflectionEntryFixtures, 8, input);

  switch (response.reflectionTab) {
    case 'hiddenDriver':
      return {
        ...response,
        data: {
          ...response.data,
          drivers: [],
          evidence: [],
          evidenceStrength: [],
        },
      };
    case 'recurringLoop':
      return {
        ...response,
        data: { ...response.data, evidence: [], steps: [] },
      };
    case 'innerTension':
      return {
        ...response,
        data: { ...response.data, tensions: [] },
      };
    case 'all':
      return response;
  }
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

  const renderResult = render(<ReflectionsScreen repository={repository} />, {
    wrapper: Wrapper,
  });

  return { ...renderResult, queryClient };
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

  it('renders the API-provided observed-entry count', async () => {
    renderReflections(
      new MockReflectionsRepository(reflectionEntryFixtures.slice(0, 5), 0),
    );

    expect(await screen.findByText('Observed across 5 entries')).toBeVisible();
    expect(
      screen.getByText(
        'Patterns taking shape across 5 entries from 14 Apr–30 Apr.',
      ),
    ).toBeVisible();
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

  it('requests only the active tab and refetches for range changes', async () => {
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockImplementation((input) =>
        Promise.resolve(result(reflectionEntryFixtures, 8, input)),
      );
    const user = userEvent.setup();
    const { queryClient } = renderReflections({ getReflection });

    await screen.findByText('Observed across 8 entries');
    expect(getReflection).toHaveBeenLastCalledWith({
      userId: 'reader-id',
      reflectionTab: 'hiddenDriver',
      range: 'all',
    });
    expect(getReflection).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));
    await screen.findByRole('heading', {
      name: 'A loop that may be keeping you stuck',
    });
    expect(getReflection).toHaveBeenLastCalledWith({
      userId: 'reader-id',
      reflectionTab: 'recurringLoop',
      range: 'all',
    });
    expect(getReflection).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole('radio', { name: 'Last 30 days' }));
    await screen.findByRole('heading', {
      name: 'A loop that may be keeping you stuck',
    });
    expect(getReflection).toHaveBeenLastCalledWith({
      userId: 'reader-id',
      reflectionTab: 'recurringLoop',
      range: '30d',
    });
    expect(getReflection).toHaveBeenCalledTimes(3);
    expect(
      queryClient.getQueryCache().find({
        queryKey: ['reflections', 'reader-id', 'recurringLoop', '30d'],
      }),
    ).toBeDefined();
    expect(
      getReflection.mock.calls.some(([input]) => input.reflectionTab === 'all'),
    ).toBe(false);
  });

  it('handles empty tab arrays without stale or misleading tab content', async () => {
    const user = userEvent.setup();
    renderReflections({
      getReflection: vi
        .fn()
        .mockImplementation((input: ReflectionRequest) =>
          Promise.resolve(emptyArrayResult(input)),
        ),
    });

    await screen.findByText(/You appear most energised when curiosity becomes/);
    expect(
      screen.queryByRole('button', { name: 'Why am I seeing this?' }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));
    expect(
      await screen.findByRole('heading', {
        name: 'No recurring loops in this range',
      }),
    ).toBeVisible();
    expect(screen.queryByText('LOOP')).not.toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(
      await screen.findByRole('heading', {
        name: 'No inner tensions in this range',
      }),
    ).toBeVisible();
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

    const resonates = screen.getByRole('button', { name: 'This resonates' });
    const partly = screen.getByRole('button', { name: 'Partly true' });
    let rejected = screen.getByRole('button', { name: 'Not true for me' });

    expect(resonates).toHaveClass('hover:bg-accent/10');
    expect(partly).toHaveClass('hover:bg-status-warning/10');

    await user.click(rejected);

    expect(rejected).toHaveAttribute('aria-pressed', 'true');
    expect(rejected).toHaveClass('radius-pill');
    expect(rejected.closest('[data-reflection-response]')).toHaveClass(
      'bg-destructive/10',
    );
    expect(
      screen.getByRole('region', { name: 'Hidden drivers reflection' }),
    ).not.toHaveClass('bg-destructive/10');
    expect(
      screen.getByText(/will not treat this as an accepted self-pattern/),
    ).toBeVisible();

    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));
    rejected = screen.getByRole('button', { name: 'Not true for me' });
    await user.click(rejected);
    expect(rejected.closest('[data-reflection-response]')).toHaveClass(
      'bg-destructive/10',
    );

    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    const tensionRejections = screen.getAllByRole('button', {
      name: 'Not true for me',
    });
    const firstTensionCard = tensionRejections[0].closest(
      '[data-reflection-response]',
    );
    const secondTensionCard = tensionRejections[1].closest(
      '[data-reflection-response]',
    );

    await user.click(tensionRejections[0]);

    expect(firstTensionCard).toHaveClass('bg-destructive/10');
    expect(firstTensionCard).not.toHaveClass(
      'border-destructive/40',
      'text-destructive',
    );
    expect(secondTensionCard).not.toHaveClass('bg-destructive/10');

    await user.click(screen.getByRole('radio', { name: 'Hidden drivers' }));
    expect(
      await screen.findByRole('button', { name: 'Not true for me' }),
    ).toHaveAttribute('aria-pressed', 'true');
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
      getReflection: vi
        .fn()
        .mockImplementation((input: ReflectionRequest) =>
          Promise.resolve(result([], 8, input)),
        ),
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
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce(result(reflectionEntryFixtures));
    const user = userEvent.setup();
    renderReflections({ getReflection });

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
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockResolvedValueOnce(result(reflectionEntryFixtures))
      .mockImplementationOnce(
        () =>
          new Promise<ReflectionApiResponse>((_resolve, reject) => {
            rejectRefresh = reject;
          }),
      );
    const user = userEvent.setup();
    renderReflections({ getReflection });

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

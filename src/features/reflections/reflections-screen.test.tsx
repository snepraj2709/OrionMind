import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { routes } from '@/config/routes';

import type {
  InsufficientInsight,
  ReflectionApiResponse,
  ReflectionFeedbackResult,
} from './api-schema';
import {
  reflectionApiFixture,
  reflectionEvidenceFixture,
  reflectionFixtureIds,
} from './fixtures';
import { ReflectionsScreen } from './reflections-screen';
import {
  HttpReflectionsRepository,
  ReflectionRequestError,
  reflectionsRepository,
  type PutReflectionFeedbackInput,
  type ReflectionsRepository,
} from './repository';
import { reflectionPolling } from './queries';

const authState = vi.hoisted(() => ({ userId: 'reader-id' }));

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ user: { id: authState.userId } }),
}));

afterEach(() => {
  authState.userId = 'reader-id';
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const insufficient: InsufficientInsight = {
  status: 'insufficient_evidence',
  reasonCode: 'INSUFFICIENT_EVIDENCE',
  message: 'There is not enough repeated evidence for this insight yet.',
};

function fixture(
  change?: (response: ReflectionApiResponse) => void,
): ReflectionApiResponse {
  const response = structuredClone(reflectionApiFixture);
  change?.(response);
  return response;
}

function setFeedback(
  response: ReflectionApiResponse,
  insightId: string,
  value: PutReflectionFeedbackInput['response'],
) {
  if (
    response.data.hiddenDriver.status === 'available' &&
    response.data.hiddenDriver.id === insightId
  ) {
    response.data.hiddenDriver.feedback = value;
  }
  if (
    response.data.recurringLoop.status === 'available' &&
    response.data.recurringLoop.id === insightId
  ) {
    response.data.recurringLoop.feedback = value;
  }
  if (response.data.innerTensions.status === 'available') {
    const tension = response.data.innerTensions.tensions.find(
      (item) => item.id === insightId,
    );
    if (tension) tension.feedback = value;
  }
}

function repositoryFor(initial = fixture()) {
  let current = structuredClone(initial);
  const getReflection = vi
    .fn<ReflectionsRepository['getReflection']>()
    .mockImplementation(async ({ range }) => ({
      ...structuredClone(current),
      range,
    }));
  const putFeedback = vi
    .fn<ReflectionsRepository['putFeedback']>()
    .mockImplementation(async (input) => {
      setFeedback(current, input.insightId, input.response);
      return {
        ...input,
        updatedAt: '2026-07-21T12:42:00Z',
      };
    });
  const recalculate = vi
    .fn<ReflectionsRepository['recalculate']>()
    .mockResolvedValue({
      status: 'accepted',
      jobId: '10000000-0000-4000-8000-000000000099',
    });
  return {
    getReflection,
    putFeedback,
    recalculate,
    repository: { getReflection, putFeedback, recalculate },
    setCurrent(next: ReflectionApiResponse) {
      current = structuredClone(next);
    },
  };
}

function renderReflections(repository?: ReflectionsRepository) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  const rendered = render(<ReflectionsScreen repository={repository} />, {
    wrapper: Wrapper,
  });
  return { ...rendered, queryClient };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

async function advancePollingIntervals(count: number) {
  for (let attempt = 0; attempt < count; attempt += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(reflectionPolling.intervalMs);
    });
  }
}

describe('ReflectionsScreen', () => {
  it('renders data returned by the default HTTP repository', async () => {
    const get = vi
      .spyOn(reflectionsRepository, 'getReflection')
      .mockResolvedValue(fixture());

    renderReflections();

    expect(
      await screen.findByRole('heading', {
        level: 2,
        name: 'You appear most energised when curiosity becomes something tangible.',
      }),
    ).toBeVisible();
    expect(screen.getByText('Supported by 2 entries')).toBeVisible();
    expect(get).toHaveBeenCalledWith({ range: 'all' }, expect.any(AbortSignal));
  });

  it('reloads the default HTTP repository when the authenticated user changes', async () => {
    const get = vi
      .spyOn(reflectionsRepository, 'getReflection')
      .mockResolvedValue(fixture());
    const { rerender } = renderReflections();

    expect(
      await screen.findByRole('heading', {
        level: 2,
        name: 'You appear most energised when curiosity becomes something tangible.',
      }),
    ).toBeVisible();

    authState.userId = 'another-reader-id';
    rerender(<ReflectionsScreen />);

    expect(
      await screen.findByRole('heading', {
        level: 2,
        name: 'You appear most energised when curiosity becomes something tangible.',
      }),
    ).toBeVisible();
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenNthCalledWith(
      1,
      { range: 'all' },
      expect.any(AbortSignal),
    );
    expect(get).toHaveBeenNthCalledWith(
      2,
      { range: 'all' },
      expect.any(AbortSignal),
    );
  });

  it('keeps the header, range, tabs, and skeleton visible while loading', () => {
    const pending = deferred<ReflectionApiResponse>();
    renderReflections({
      getReflection: vi.fn(() => pending.promise),
      putFeedback: vi.fn(),
      recalculate: vi.fn(),
    });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Reflections',
    );
    expect(screen.getByRole('radio', { name: 'Latest 90 days' })).toBeVisible();
    expect(screen.getByRole('radio', { name: 'Hidden drivers' })).toBeVisible();
    const loadingHeading = screen.getByRole('heading', { name: 'Loading' });
    expect(loadingHeading.closest('[data-slot="card"]')).toBeInTheDocument();
  });

  it('fetches once per user and range while tabs remain local and keyboard accessible', async () => {
    const { getReflection, recalculate, repository } = repositoryFor();
    const user = userEvent.setup();
    const { queryClient } = renderReflections(repository);

    await screen.findByText('Supported by 2 entries');
    expect(getReflection).toHaveBeenCalledTimes(1);
    expect(recalculate).not.toHaveBeenCalled();
    expect(getReflection).toHaveBeenLastCalledWith(
      { range: 'all' },
      expect.any(AbortSignal),
    );
    expect(
      queryClient.getQueryCache().find({
        queryKey: ['reflections', 'reader-id', 'all'],
      }),
    ).toBeDefined();

    const hiddenTab = screen.getByRole('radio', { name: 'Hidden drivers' });
    hiddenTab.focus();
    await user.keyboard('{ArrowRight}{Enter}');
    expect(
      screen.getByRole('heading', {
        name: 'A loop that may be keeping you stuck',
      }),
    ).toBeVisible();
    expect(getReflection).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getByRole('heading', { name: 'Novelty' })).toBeVisible();
    expect(getReflection).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('radio', { name: 'Last 30 days' }));
    await waitFor(() => expect(getReflection).toHaveBeenCalledTimes(2));
    expect(getReflection).toHaveBeenLastCalledWith(
      { range: '30d' },
      expect.any(AbortSignal),
    );
    expect(recalculate).not.toHaveBeenCalled();
    expect(
      queryClient.getQueryCache().find({
        queryKey: ['reflections', 'reader-id', '30d'],
      }),
    ).toBeDefined();
  });

  it('describes the bounded 90-day basis without applying its count to shorter ranges', async () => {
    const { repository } = repositoryFor();
    const user = userEvent.setup();
    renderReflections(repository);

    expect(
      await screen.findByText(
        'Patterns taking shape across 8 reflective entries in your latest 90-day reflection window (14 Jul–21 Jul).',
      ),
    ).toBeVisible();
    await user.click(screen.getByRole('radio', { name: 'Last 7 days' }));
    expect(
      await screen.findByText(
        'Patterns shown for 14 Jul–21 Jul, drawn from your latest 90-day reflection window.',
      ),
    ).toBeVisible();
    expect(
      screen.queryByText(/across 8 reflective entries/),
    ).not.toBeInTheDocument();
  });

  it('uses the snapshot evidence-entry count rather than bounded evidence rows', async () => {
    const response = fixture((value) => {
      if (value.data.hiddenDriver.status === 'available') {
        value.data.hiddenDriver.evidenceEntryCount = 7;
        value.data.hiddenDriver.evidence =
          value.data.hiddenDriver.evidence.slice(0, 1);
      }
    });
    renderReflections(repositoryFor(response).repository);

    expect(await screen.findByText('Supported by 7 entries')).toBeVisible();
  });

  it('renders persisted feedback and opens only the selected insight evidence', async () => {
    const user = userEvent.setup();
    renderReflections(repositoryFor().repository);
    await screen.findByText('Supported by 2 entries');

    await user.click(
      screen.getByRole('button', { name: 'View supporting entries' }),
    );
    expect(screen.getByText(reflectionEvidenceFixture[0]!.quote)).toBeVisible();
    expect(
      screen.queryByText(reflectionEvidenceFixture[2]!.quote),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close' }));

    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));
    expect(screen.getByRole('button', { name: 'Partly true' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    const evidenceButtons = screen.getAllByRole('button', {
      name: 'View supporting entries',
    });
    await user.click(evidenceButtons[1]!);
    expect(screen.getByText(reflectionEvidenceFixture[2]!.quote)).toBeVisible();
    expect(
      screen.queryByText(reflectionEvidenceFixture[0]!.quote),
    ).not.toBeInTheDocument();
  });

  it('renders first-pending insufficiency without hiding tabs', async () => {
    const user = userEvent.setup();
    const response = fixture((value) => {
      value.reflectionState = 'first_reflection_pending';
      value.processingState = 'pending';
      value.snapshot = null;
      value.data.hiddenDriver = {
        ...insufficient,
        reasonCode: 'DRIVER_NOT_REPEATED',
      };
      value.data.recurringLoop = {
        ...insufficient,
        reasonCode: 'LOOP_NOT_REPEATED',
      };
      value.data.innerTensions = {
        ...insufficient,
        reasonCode: 'BOTH_SIDES_NOT_SUPPORTED',
      };
    });
    renderReflections(repositoryFor(response).repository);

    expect(
      await screen.findByText('Your first reflection is taking shape'),
    ).toBeVisible();
    expect(screen.getByText(insufficient.message)).toBeVisible();
    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));
    expect(screen.getByText(insufficient.message)).toBeVisible();
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getByText(insufficient.message)).toBeVisible();
  });

  it('keeps available tabs usable when one section is insufficient', async () => {
    const response = fixture((value) => {
      value.data.recurringLoop = {
        ...insufficient,
        reasonCode: 'LOOP_NOT_REPEATED',
      };
    });
    const { getReflection, repository } = repositoryFor(response);
    const user = userEvent.setup();
    renderReflections(repository);

    await screen.findByText('Supported by 2 entries');
    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));
    expect(screen.getByText(insufficient.message)).toBeVisible();
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getAllByText('Possible integration')).toHaveLength(2);
    expect(getReflection).toHaveBeenCalledTimes(1);
  });

  it('does not live-announce a persisted rejection when its tab remounts', async () => {
    const user = userEvent.setup();
    renderReflections(repositoryFor().repository);
    await screen.findByText('Supported by 2 entries');

    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    const explanation = screen.getByText(/Marked as not true for you/);
    expect(explanation).not.toHaveAttribute('aria-live');
    await user.click(screen.getByRole('radio', { name: 'Hidden drivers' }));
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getByText(/Marked as not true for you/)).not.toHaveAttribute(
      'aria-live',
    );
  });

  it.each([
    ['pending', 'Updating your reflections'],
    ['failed', 'Orion could not refresh these reflections'],
  ] as const)(
    'keeps stale cards visible when processing is %s',
    async (state, copy) => {
      const response = fixture((value) => {
        value.reflectionState = 'stale';
        value.processingState = state;
        if (value.snapshot) value.snapshot.isStale = true;
      });
      renderReflections(repositoryFor(response).repository);

      expect(await screen.findByText(copy, { exact: false })).toBeVisible();
      expect(screen.getByText('Supported by 2 entries')).toBeVisible();
    },
  );

  it('uses the API-safe message for insufficient reflective content', async () => {
    const response = fixture((value) => {
      value.reflectionState = 'insufficient_reflective_content';
      value.snapshot = null;
      value.data.hiddenDriver = {
        status: 'insufficient_evidence',
        reasonCode: 'NOT_ENOUGH_REFLECTIVE_CONTENT',
        message:
          'There is not enough personal reflection to identify a meaningful pattern yet.',
      };
      value.data.recurringLoop = insufficient;
      value.data.innerTensions = insufficient;
    });
    renderReflections(repositoryFor(response).repository);

    expect(
      await screen.findByText(
        'There is not enough personal reflection to identify a meaningful pattern yet.',
      ),
    ).toBeVisible();
    expect(
      screen.getByRole('link', { name: 'Write a new entry' }),
    ).toHaveAttribute('href', routes.newEntry.path);
    expect(
      screen.queryByRole('radio', { name: 'Hidden drivers' }),
    ).not.toBeInTheDocument();
  });

  it('shows a technical initial error and retry without fabricating insufficiency', async () => {
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockRejectedValueOnce(new Error('503'))
      .mockResolvedValueOnce(fixture());
    const user = userEvent.setup();
    renderReflections({
      getReflection,
      putFeedback: vi.fn(),
      recalculate: vi.fn(),
    });

    expect(
      await screen.findByText('Reflections are unavailable'),
    ).toBeVisible();
    expect(
      screen.queryByText('More personal reflection is needed'),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Supported by 2 entries')).toBeVisible();
  });

  it('treats a malformed successful response as a technical load failure', async () => {
    const repository = new HttpReflectionsRepository(
      vi.fn().mockResolvedValue(Response.json({ data: {} })),
    );

    renderReflections(repository);

    expect(
      await screen.findByText('Reflections are unavailable'),
    ).toBeVisible();
    expect(
      screen.queryByText('More personal reflection is needed'),
    ).not.toBeInTheDocument();
  });

  it('shows a no-results state for available hidden drivers and loops without range evidence', async () => {
    const response = fixture((value) => {
      if (value.data.hiddenDriver.status === 'available') {
        value.data.hiddenDriver.evidence = [];
      }
      if (value.data.recurringLoop.status === 'available') {
        value.data.recurringLoop.evidence = [];
      }
    });
    const user = userEvent.setup();
    renderReflections(repositoryFor(response).repository);

    expect(
      await screen.findByText('No supporting entries in this range'),
    ).toBeVisible();
    expect(
      screen.getByText(
        'No supporting entries are available for this pattern in the latest 90-day reflection window.',
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole('group', { name: 'Hidden driver feedback' }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));
    expect(
      screen.getByText('No supporting entries in this range'),
    ).toBeVisible();
    expect(
      screen.queryByRole('group', { name: 'Recurring loop feedback' }),
    ).not.toBeInTheDocument();
  });

  it('renders zero, one, and every returned inner tension', async () => {
    const user = userEvent.setup();
    const zero = fixture((value) => {
      value.data.innerTensions = {
        ...insufficient,
        reasonCode: 'BOTH_SIDES_NOT_SUPPORTED',
      };
    });
    const first = renderReflections(repositoryFor(zero).repository);
    await screen.findByText('Supported by 2 entries');
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getByText(insufficient.message)).toBeVisible();
    first.unmount();

    const one = fixture((value) => {
      if (value.data.innerTensions.status === 'available') {
        value.data.innerTensions.tensions =
          value.data.innerTensions.tensions.slice(0, 1);
      }
    });
    const second = renderReflections(repositoryFor(one).repository);
    await screen.findByText('Supported by 2 entries');
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getAllByText('Possible integration')).toHaveLength(1);
    second.unmount();

    renderReflections(repositoryFor().repository);
    await screen.findByText('Supported by 2 entries');
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getAllByText('Possible integration')).toHaveLength(2);
  });

  it('filters zero-evidence inner tensions and falls back when none have range evidence', async () => {
    const user = userEvent.setup();
    const mixed = fixture((value) => {
      if (value.data.innerTensions.status === 'available') {
        value.data.innerTensions.tensions[0]!.evidence = [];
      }
    });
    const first = renderReflections(repositoryFor(mixed).repository);
    await screen.findByText('Supported by 2 entries');
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(
      screen.queryByRole('heading', { name: 'Novelty' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Belonging' })).toBeVisible();
    expect(screen.getAllByText('Possible integration')).toHaveLength(1);
    first.unmount();

    const empty = fixture((value) => {
      if (value.data.innerTensions.status === 'available') {
        value.data.innerTensions.tensions.forEach((tension) => {
          tension.evidence = [];
        });
      }
    });
    renderReflections(repositoryFor(empty).repository);
    await screen.findByText('Supported by 2 entries');
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(
      screen.getByText('No supporting entries in this range'),
    ).toBeVisible();
    expect(screen.queryByText('Possible integration')).not.toBeInTheDocument();
  });

  it('optimistically saves once, disables only that insight, and reconciles success', async () => {
    const current = fixture();
    const pending = deferred<ReflectionFeedbackResult>();
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockImplementation(async ({ range }) => ({
        ...structuredClone(current),
        range,
      }));
    const putFeedback = vi
      .fn<ReflectionsRepository['putFeedback']>()
      .mockImplementation((input) =>
        pending.promise.then((result) => {
          setFeedback(current, input.insightId, input.response);
          return result;
        }),
      );
    const user = userEvent.setup();
    const { queryClient } = renderReflections({
      getReflection,
      putFeedback,
      recalculate: vi.fn(),
    });
    await screen.findByText('Supported by 2 entries');
    const otherRange = fixture((value) => {
      value.range = '30d';
    });
    const otherRangeKey = ['reflections', 'reader-id', '30d'] as const;
    queryClient.setQueryData(otherRangeKey, otherRange);

    const rejected = screen.getByRole('button', { name: 'Not true for me' });
    await user.click(rejected);
    expect(rejected).toHaveAttribute('aria-pressed', 'true');
    expect(rejected).toBeDisabled();
    expect(rejected.closest('[role="group"]')).toHaveAttribute(
      'aria-busy',
      'true',
    );
    await user.click(rejected);
    expect(putFeedback).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(
      screen.getAllByRole('button', { name: 'This resonates' })[0],
    ).toBeEnabled();

    pending.resolve({
      snapshotId: reflectionFixtureIds.snapshot,
      insightId: reflectionFixtureIds.hiddenDriver,
      response: 'rejected',
      updatedAt: '2026-07-21T12:42:00Z',
    });
    await user.click(screen.getByRole('radio', { name: 'Hidden drivers' }));
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Not true for me' }),
      ).toBeEnabled(),
    );
    expect(
      screen.getByRole('button', { name: 'Not true for me' }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(queryClient.getQueryData(otherRangeKey)).toEqual(otherRange);
    expect(queryClient.getQueryState(otherRangeKey)?.isInvalidated).toBe(false);
  });

  it('rolls back failed feedback and exposes an inline polite error', async () => {
    const pending = deferred<ReflectionFeedbackResult>();
    const { getReflection } = repositoryFor();
    const user = userEvent.setup();
    renderReflections({
      getReflection,
      putFeedback: vi.fn(() => pending.promise),
      recalculate: vi.fn(),
    });
    await screen.findByText('Supported by 2 entries');

    const rejected = screen.getByRole('button', { name: 'Not true for me' });
    await user.click(rejected);
    expect(rejected).toHaveAttribute('aria-pressed', 'true');
    pending.reject(new Error('Unavailable'));

    expect(
      await screen.findByText(
        'Your feedback could not be saved. Please try again.',
      ),
    ).toHaveAttribute('role', 'status');
    expect(
      screen.getByRole('button', { name: 'Not true for me' }),
    ).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Supported by 2 entries')).toBeVisible();
  });

  it('renders processing, unavailable, and available sections independently', async () => {
    const response = fixture((value) => {
      value.processingState = 'pending';
      value.data.hiddenDriver = {
        status: 'processing',
        message: 'The hidden driver is still being recalculated.',
      };
      value.data.recurringLoop = {
        status: 'unavailable',
        reasonCode: 'TECHNICAL_FAILURE',
        message: 'The recurring loop is temporarily unavailable.',
        retryable: true,
      };
    });
    const user = userEvent.setup();
    renderReflections(repositoryFor(response).repository);

    expect(
      await screen.findByText('The hidden driver is still being recalculated.'),
    ).toBeVisible();
    await user.click(screen.getByRole('radio', { name: 'Recurring loops' }));
    expect(
      screen.getByText('The recurring loop is temporarily unavailable.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeDisabled();
    await user.click(screen.getByRole('radio', { name: 'Inner tensions' }));
    expect(screen.getAllByText('Possible integration')).toHaveLength(2);
  });

  it('posts recalculation, refetches immediately, and polls only while processing', async () => {
    vi.useFakeTimers();
    const available = fixture();
    const processing = fixture((value) => {
      value.reflectionState = 'stale';
      value.processingState = 'pending';
      if (value.snapshot) value.snapshot.isStale = true;
    });
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockResolvedValueOnce(available)
      .mockResolvedValueOnce(processing)
      .mockResolvedValue(available);
    const recalculate = vi
      .fn<ReflectionsRepository['recalculate']>()
      .mockResolvedValue({
        status: 'accepted',
        jobId: '10000000-0000-4000-8000-000000000099',
      });
    renderReflections({
      getReflection,
      putFeedback: vi.fn(),
      recalculate,
    });
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(1);
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'Refresh reflections' }),
    );
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(recalculate).toHaveBeenCalledTimes(1);
    expect(recalculate).toHaveBeenCalledWith(expect.any(AbortSignal));
    expect(getReflection).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Updating your reflections')).toBeVisible();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(reflectionPolling.intervalMs);
    });

    expect(getReflection).toHaveBeenCalledTimes(3);
    expect(screen.getByText('Supported by 2 entries')).toBeVisible();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(reflectionPolling.intervalMs * 2);
    });
    expect(getReflection).toHaveBeenCalledTimes(3);
  });

  it('bounds automatic GET polling and never posts on an ordinary processing view', async () => {
    vi.useFakeTimers();
    const processing = fixture((value) => {
      value.reflectionState = 'first_reflection_pending';
      value.processingState = 'pending';
      value.snapshot = null;
      value.data.hiddenDriver = {
        status: 'processing',
        message: 'Still processing.',
      };
    });
    const { getReflection, recalculate, repository, setCurrent } =
      repositoryFor(processing);
    renderReflections(repository);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    await advancePollingIntervals(reflectionPolling.maxAttempts + 2);
    const boundedCallCount = getReflection.mock.calls.length;
    expect(boundedCallCount).toBeGreaterThan(1);
    expect(boundedCallCount).toBeLessThanOrEqual(
      reflectionPolling.maxAttempts + 1,
    );
    expect(recalculate).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        'This update is taking longer than expected. Check again without starting another recalculation.',
      ),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Check again' })).toBeEnabled();

    await advancePollingIntervals(reflectionPolling.maxAttempts);
    expect(getReflection).toHaveBeenCalledTimes(boundedCallCount);

    setCurrent(fixture());
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }));
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(screen.getByText('Supported by 2 entries')).toBeVisible();
    expect(getReflection).toHaveBeenCalledTimes(boundedCallCount + 1);
    expect(recalculate).not.toHaveBeenCalled();
  });

  it('counts failed polling reads toward the cap and recovers with a cached GET retry', async () => {
    vi.useFakeTimers();
    const processing = fixture((value) => {
      value.reflectionState = 'stale';
      value.processingState = 'pending';
      if (value.snapshot) value.snapshot.isStale = true;
    });
    const available = fixture();
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockResolvedValueOnce(processing)
      .mockRejectedValue(new Error('503'));
    const recalculate = vi
      .fn<ReflectionsRepository['recalculate']>()
      .mockResolvedValue({
        status: 'accepted',
        jobId: '10000000-0000-4000-8000-000000000099',
      });
    renderReflections({
      getReflection,
      putFeedback: vi.fn(),
      recalculate,
    });
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(1);
    });

    await advancePollingIntervals(reflectionPolling.maxAttempts + 2);
    const boundedCallCount = getReflection.mock.calls.length;

    expect(boundedCallCount).toBeLessThanOrEqual(
      reflectionPolling.maxAttempts + 1,
    );
    expect(screen.getByText(/Showing the last available view/)).toBeVisible();
    expect(recalculate).not.toHaveBeenCalled();

    await advancePollingIntervals(reflectionPolling.maxAttempts);
    expect(getReflection).toHaveBeenCalledTimes(boundedCallCount);

    getReflection.mockResolvedValue(available);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(screen.getByText('Supported by 2 entries')).toBeVisible();
    expect(getReflection).toHaveBeenCalledTimes(boundedCallCount + 1);
  });

  it('cancels an in-flight polling read when the range changes', async () => {
    const pending = deferred<ReflectionApiResponse>();
    let pollingSignal: AbortSignal | undefined;
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockResolvedValueOnce(fixture())
      .mockImplementationOnce((_input, signal) => {
        pollingSignal = signal;
        signal?.addEventListener('abort', () => {
          pending.reject(new DOMException('Aborted', 'AbortError'));
        });
        return pending.promise;
      })
      .mockImplementation(async ({ range }) => ({
        ...fixture(),
        range,
      }));
    const recalculate = vi
      .fn<ReflectionsRepository['recalculate']>()
      .mockResolvedValue({
        status: 'accepted',
        jobId: '10000000-0000-4000-8000-000000000099',
      });
    const user = userEvent.setup();
    renderReflections({
      getReflection,
      putFeedback: vi.fn(),
      recalculate,
    });
    await screen.findByText('Supported by 2 entries');

    await user.click(
      screen.getByRole('button', { name: 'Refresh reflections' }),
    );
    await waitFor(() => expect(getReflection).toHaveBeenCalledTimes(2));
    await user.click(screen.getByRole('radio', { name: 'Last 30 days' }));

    await waitFor(() => expect(pollingSignal?.aborted).toBe(true));
    await waitFor(() => expect(getReflection).toHaveBeenCalledTimes(3));
    expect(getReflection).toHaveBeenLastCalledWith(
      { range: '30d' },
      expect.any(AbortSignal),
    );
    expect(recalculate).toHaveBeenCalledTimes(1);
  });

  it.each([
    [
      new ReflectionRequestError(
        'Reflection recalculation request failed: 409',
        409,
        'REFLECTION_ALREADY_CURRENT',
      ),
      'These reflections are already up to date.',
      false,
    ],
    [
      new ReflectionRequestError(
        'Reflection recalculation request failed: 503',
        503,
        'REFLECTION_RECALCULATION_UNAVAILABLE',
      ),
      'Orion could not start recalculating your reflections.',
      true,
    ],
    [
      new ReflectionRequestError(
        'Reflection recalculation request failed: 409',
        409,
        'REFLECTION_NOT_ELIGIBLE',
      ),
      'There is not enough reflective evidence to recalculate these reflections yet.',
      false,
    ],
  ] as const)(
    'keeps the last good cards when recalculation fails',
    async (error, message, retryable) => {
      const { repository } = repositoryFor();
      repository.recalculate = vi.fn().mockRejectedValue(error);
      const user = userEvent.setup();
      renderReflections(repository);
      await screen.findByText('Supported by 2 entries');

      await user.click(
        screen.getByRole('button', { name: 'Refresh reflections' }),
      );

      expect(await screen.findByText(message, { exact: false })).toBeVisible();
      expect(screen.getByText('Supported by 2 entries')).toBeVisible();
      if (retryable) {
        expect(
          screen.getByRole('button', { name: 'Retry' }),
        ).toBeInTheDocument();
      } else {
        expect(
          screen.queryByRole('button', { name: 'Retry' }),
        ).not.toBeInTheDocument();
      }
    },
  );

  it('preserves cards when a background refresh fails', async () => {
    const refresh = deferred<ReflectionApiResponse>();
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockResolvedValueOnce(fixture())
      .mockImplementationOnce(() => refresh.promise);
    const user = userEvent.setup();
    renderReflections({
      getReflection,
      putFeedback: vi.fn(),
      recalculate: vi.fn().mockResolvedValue({
        status: 'accepted',
        jobId: '10000000-0000-4000-8000-000000000099',
      }),
    });
    await screen.findByText('Supported by 2 entries');

    await user.click(
      screen.getByRole('button', { name: 'Refresh reflections' }),
    );
    refresh.reject(new Error('Unavailable'));

    expect(
      await screen.findByText(/Showing the last available view/),
    ).toBeVisible();
    expect(screen.getByText('Supported by 2 entries')).toBeVisible();
  });

  it('keeps one page heading and one visible reflection panel', async () => {
    renderReflections(repositoryFor().repository);
    await screen.findByText('Supported by 2 entries');

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole('region', { name: /reflection$/ })).toHaveLength(
      1,
    );
    expect(
      within(
        screen.getByRole('region', { name: 'Hidden drivers reflection' }),
      ).getByRole('group', { name: 'Hidden driver feedback' }),
    ).toBeVisible();
  });
});

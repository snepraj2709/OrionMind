import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
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
  reflectionsRepository,
  type PutReflectionFeedbackInput,
  type ReflectionsRepository,
} from './repository';

vi.mock('@/features/auth', () => ({
  useAuth: () => ({ user: { id: 'reader-id' } }),
}));

afterEach(() => {
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
  return {
    getReflection,
    putFeedback,
    repository: { getReflection, putFeedback },
    setCurrent(next: ReflectionApiResponse) {
      current = structuredClone(next);
    },
  };
}

function renderReflections(
  repository?: ReflectionsRepository,
  reflectionsEnabled = true,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  const rendered = render(
    <ReflectionsScreen
      reflectionsEnabled={reflectionsEnabled}
      repository={repository}
    />,
    { wrapper: Wrapper },
  );
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

describe('ReflectionsScreen', () => {
  it('renders an accessible unavailable state without reading or writing when disabled', () => {
    const { getReflection, putFeedback, repository } = repositoryFor();

    renderReflections(repository, false);

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Reflections',
    );
    const unavailable = screen.getByRole('status');
    expect(unavailable).toBeVisible();
    expect(
      within(unavailable).getByRole('heading', {
        name: 'Reflections aren’t available yet',
      }),
    ).toBeVisible();
    expect(
      screen.queryByText('Supported by 2 entries'),
    ).not.toBeInTheDocument();
    expect(getReflection).not.toHaveBeenCalled();
    expect(putFeedback).not.toHaveBeenCalled();
  });

  it('defaults to the real HTTP repository', async () => {
    const get = vi
      .spyOn(reflectionsRepository, 'getReflection')
      .mockResolvedValue(fixture());
    vi.spyOn(reflectionsRepository, 'putFeedback').mockResolvedValue({
      snapshotId: reflectionFixtureIds.snapshot,
      insightId: reflectionFixtureIds.hiddenDriver,
      response: 'resonates',
      updatedAt: '2026-07-21T12:42:00Z',
    });

    renderReflections();

    expect(await screen.findByText('Supported by 2 entries')).toBeVisible();
    expect(get).toHaveBeenCalledWith({ range: 'all' });
  });

  it('keeps the header, range, tabs, and skeleton visible while loading', () => {
    const pending = deferred<ReflectionApiResponse>();
    renderReflections({
      getReflection: vi.fn(() => pending.promise),
      putFeedback: vi.fn(),
    });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Reflections',
    );
    expect(screen.getByRole('radio', { name: 'Latest 90 days' })).toBeVisible();
    expect(screen.getByRole('radio', { name: 'Hidden drivers' })).toBeVisible();
    expect(screen.getByRole('status', { name: 'Loading items' })).toBeVisible();
  });

  it('fetches once per user and range while tabs remain local and keyboard accessible', async () => {
    const { getReflection, repository } = repositoryFor();
    const user = userEvent.setup();
    const { queryClient } = renderReflections(repository);

    await screen.findByText('Supported by 2 entries');
    expect(getReflection).toHaveBeenCalledTimes(1);
    expect(getReflection).toHaveBeenLastCalledWith({ range: 'all' });
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
    expect(getReflection).toHaveBeenLastCalledWith({ range: '30d' });
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

  it('counts distinct supporting entries rather than evidence rows', async () => {
    const response = fixture((value) => {
      if (value.data.hiddenDriver.status === 'available') {
        value.data.hiddenDriver.evidence[1]!.entryDate =
          value.data.hiddenDriver.evidence[0]!.entryDate;
      }
    });
    renderReflections(repositoryFor(response).repository);

    expect(await screen.findByText('Supported by 1 entry')).toBeVisible();
    expect(
      screen.queryByText('Supported by 2 entries'),
    ).not.toBeInTheDocument();
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
    renderReflections({ getReflection, putFeedback: vi.fn() });

    expect(
      await screen.findByText('Reflections are unavailable'),
    ).toBeVisible();
    expect(
      screen.queryByText('More personal reflection is needed'),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Supported by 2 entries')).toBeVisible();
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
    const { queryClient } = renderReflections({ getReflection, putFeedback });
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

  it('preserves cards when a background refresh fails', async () => {
    const refresh = deferred<ReflectionApiResponse>();
    const getReflection = vi
      .fn<ReflectionsRepository['getReflection']>()
      .mockResolvedValueOnce(fixture())
      .mockImplementationOnce(() => refresh.promise);
    const user = userEvent.setup();
    renderReflections({ getReflection, putFeedback: vi.fn() });
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

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { routes } from '@/config/routes';

import type { EntrySummary } from './model';
import { NewEntryScreen } from './new-entry-screen';
import type { EntryComposerRepository } from './repository';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

const createdEntry: EntrySummary = {
  id: 'new-entry',
  content: 'A newly created entry.',
  date: '2026-07-21',
  inputType: 'text',
  status: 'pending',
  themes: [],
};

function createRepository(
  overrides: Partial<EntryComposerRepository> = {},
): EntryComposerRepository {
  return {
    getTextDraft: vi.fn().mockResolvedValue({ content: null, updatedAt: null }),
    saveTextDraft: vi.fn().mockImplementation(async (content: string) => ({
      content,
      updatedAt: '2026-07-21T10:00:00Z',
    })),
    discardTextDraft: vi.fn().mockResolvedValue({
      content: null,
      updatedAt: null,
    }),
    createTextEntry: vi.fn().mockResolvedValue(createdEntry),
    createVoiceEntry: vi
      .fn()
      .mockResolvedValue({ ...createdEntry, inputType: 'voice' }),
    ...overrides,
  };
}

function renderNewEntry(repository = createRepository()) {
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

  return {
    repository,
    queryClient,
    ...render(<NewEntryScreen repository={repository} />, { wrapper: Wrapper }),
  };
}

async function editableTextbox() {
  const textbox = screen.getByRole('textbox', { name: 'Your entry' });
  await waitFor(() => expect(textbox).toBeEnabled());
  return textbox;
}

function installMicrophone() {
  const stopTrack = vi.fn();
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn().mockResolvedValue({
        getTracks: () => [{ stop: stopTrack }],
      }),
    },
  });

  class MockMediaRecorder {
    mimeType = 'audio/webm;codecs=opus';
    ondataavailable: ((event: BlobEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    onstop: ((event: Event) => void) | null = null;
    state: RecordingState = 'inactive';

    start() {
      this.state = 'recording';
    }
    pause() {
      this.state = 'paused';
    }
    resume() {
      this.state = 'recording';
    }
    stop() {
      this.state = 'inactive';
      this.ondataavailable?.({
        data: new Blob(['voice'], { type: this.mimeType }),
      } as BlobEvent);
      this.onstop?.(new Event('stop'));
    }
  }

  vi.stubGlobal('MediaRecorder', MockMediaRecorder);
  return { stopTrack };
}

async function recordVoice(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('radio', { name: 'Record' }));
  await user.click(screen.getByRole('button', { name: 'Start' }));
  await user.click(await screen.findByRole('button', { name: 'Stop' }));
  await screen.findByText('Recording ready');
}

afterEach(() => {
  vi.useRealTimers();
  push.mockReset();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'mediaDevices');
  vi.restoreAllMocks();
});

describe('NewEntryScreen', () => {
  it('restores the server draft before enabling editing', async () => {
    renderNewEntry(
      createRepository({
        getTextDraft: vi.fn().mockResolvedValue({
          content: 'Restored words',
          updatedAt: '2026-07-21T10:00:00Z',
        }),
      }),
    );

    expect(screen.getByText('Restoring saved draft')).toBeVisible();
    const textbox = await editableTextbox();
    const draftStatus = screen.getByRole('status');
    const modeControl = screen.getByRole('radiogroup', {
      name: 'Entry mode',
    });

    expect(textbox).toHaveValue('Restored words');
    expect(draftStatus).toHaveTextContent('Draft saved');
    expect(draftStatus.parentElement).toBe(modeControl.parentElement);
    expect(textbox.closest('form')).not.toContainElement(draftStatus);
  });

  it('shows a retryable restore error', async () => {
    const getTextDraft = vi
      .fn()
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce({ content: 'Recovered', updatedAt: null });
    const user = userEvent.setup();
    renderNewEntry(createRepository({ getTextDraft }));

    expect(
      await screen.findByText('Your saved draft could not be restored.'),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await editableTextbox()).toHaveValue('Recovered');
    expect(getTextDraft).toHaveBeenCalledTimes(2);
  });

  it('autosaves after 750 ms and does not warn for synchronized text', async () => {
    const repository = createRepository();
    renderNewEntry(repository);
    const textbox = await editableTextbox();
    vi.useFakeTimers();

    fireEvent.change(textbox, { target: { value: 'Autosaved thought' } });
    await act(async () => {
      vi.advanceTimersByTime(749);
    });
    expect(repository.saveTextDraft).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(repository.saveTextDraft).toHaveBeenCalledWith('Autosaved thought');
    expect(screen.getByText('Draft saved')).toBeVisible();

    const unloadEvent = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unloadEvent);
    expect(unloadEvent.defaultPrevented).toBe(false);
  });

  it('flushes the exact draft before POST and redirects without DELETE', async () => {
    const calls: string[] = [];
    const repository = createRepository({
      saveTextDraft: vi.fn(async (content: string) => {
        calls.push(`PUT:${content}`);
        return { content, updatedAt: null };
      }),
      createTextEntry: vi.fn(async ({ content }) => {
        calls.push(`POST:${content}`);
        return createdEntry;
      }),
    });
    const user = userEvent.setup();
    renderNewEntry(repository);
    await user.type(await editableTextbox(), '  Exact thought  ');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(push).toHaveBeenCalledWith(routes.entries.path));
    expect(calls).toEqual(['PUT:Exact thought', 'POST:Exact thought']);
    expect(repository.discardTextDraft).not.toHaveBeenCalled();
  });

  it('does not POST and retains writing when draft saving fails', async () => {
    const repository = createRepository({
      saveTextDraft: vi.fn().mockRejectedValue(new Error('Unavailable')),
    });
    const user = userEvent.setup();
    renderNewEntry(repository);
    const textbox = await editableTextbox();
    await user.type(textbox, 'Keep these words safe.');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText(/Your draft could not be synchronized/),
    ).toBeVisible();
    expect(repository.createTextEntry).not.toHaveBeenCalled();
    expect(textbox).toHaveValue('Keep these words safe.');
  });

  it('cancels or confirms discard and only clears after DELETE succeeds', async () => {
    const repository = createRepository({
      getTextDraft: vi.fn().mockResolvedValue({
        content: 'Saved draft',
        updatedAt: null,
      }),
    });
    const confirm = vi
      .spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    const user = userEvent.setup();
    renderNewEntry(repository);
    const textbox = await editableTextbox();

    await user.click(screen.getByRole('button', { name: 'Discard draft' }));
    expect(repository.discardTextDraft).not.toHaveBeenCalled();
    expect(textbox).toHaveValue('Saved draft');
    await user.click(screen.getByRole('button', { name: 'Discard draft' }));
    await waitFor(() => expect(repository.discardTextDraft).toHaveBeenCalled());
    expect(textbox).toHaveValue('');
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it('warns only while local text is not synchronized', async () => {
    const user = userEvent.setup();
    renderNewEntry();
    await user.type(await editableTextbox(), 'Unfinished thought');

    const unloadEvent = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unloadEvent);
    expect(unloadEvent.defaultPrevented).toBe(true);
  });

  it('reuses one voice key across retries and creates a new key after recording again', async () => {
    installMicrophone();
    const createVoiceEntry = vi
      .fn<EntryComposerRepository['createVoiceEntry']>()
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValue({ ...createdEntry, inputType: 'voice' });
    const user = userEvent.setup();
    renderNewEntry(createRepository({ createVoiceEntry }));
    await recordVoice(user);

    await user.click(screen.getByRole('button', { name: 'Add' }));
    await screen.findByText(/voice entry could not be added/i);
    await user.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(createVoiceEntry).toHaveBeenCalledTimes(2));
    const firstKey = createVoiceEntry.mock.calls[0]?.[0].idempotencyKey;
    expect(createVoiceEntry.mock.calls[1]?.[0].idempotencyKey).toBe(firstKey);
    expect(push).toHaveBeenCalledWith(routes.entries.path);

    push.mockReset();
    createVoiceEntry.mockClear();
    await user.click(screen.getByRole('radio', { name: 'Record' }));
    await user.click(screen.getByRole('button', { name: 'Start' }));
    await user.click(await screen.findByRole('button', { name: 'Stop' }));
    await user.click(await screen.findByRole('button', { name: 'Add' }));
    await waitFor(() => expect(createVoiceEntry).toHaveBeenCalledTimes(1));
    expect(createVoiceEntry.mock.calls[0]?.[0].idempotencyKey).not.toBe(
      firstKey,
    );
  });
});

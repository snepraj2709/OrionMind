import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { routes } from '@/config/routes';

import type { EntrySummary } from './model';
import { NewEntryScreen } from './new-entry-screen';
import type { EntriesRepository } from './repository';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

const createdEntry: EntrySummary = {
  id: 'new-entry',
  content: 'A newly created entry.',
  date: '2025-07-19',
  inputType: 'text',
  status: 'processing',
  themes: [],
};

function createRepository(
  overrides: Partial<EntriesRepository> = {},
): EntriesRepository {
  return {
    createTextEntry: vi.fn().mockResolvedValue(createdEntry),
    createVoiceEntry: vi
      .fn()
      .mockResolvedValue({ ...createdEntry, inputType: 'voice' }),
    listEntries: vi.fn().mockResolvedValue({
      items: [],
      total: 0,
      totalAll: 0,
    }),
    getEntry: vi.fn().mockResolvedValue(null),
    decideExtractedItem: vi.fn(),
    retryEntry: vi.fn(),
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
    ...render(<NewEntryScreen repository={repository} />, { wrapper: Wrapper }),
  };
}

function installMicrophone(options: { denied?: boolean } = {}) {
  const stopTrack = vi.fn();
  const getUserMedia = options.denied
    ? vi
        .fn()
        .mockRejectedValue(
          new DOMException('Microphone access denied', 'NotAllowedError'),
        )
    : vi.fn().mockResolvedValue({
        getTracks: () => [{ stop: stopTrack }],
      });

  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });

  class MockMediaRecorder {
    mimeType = 'audio/webm';
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
      this.ondataavailable?.({ data: new Blob(['voice']) } as BlobEvent);
      this.onstop?.(new Event('stop'));
    }
  }

  vi.stubGlobal('MediaRecorder', MockMediaRecorder);
  return { getUserMedia, stopTrack };
}

afterEach(() => {
  push.mockReset();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'mediaDevices');
});

describe('NewEntryScreen', () => {
  it('validates and creates a text entry through the repository', async () => {
    const repository = createRepository();
    const user = userEvent.setup();
    renderNewEntry(repository);

    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(
      await screen.findByText('Write something before adding this entry.'),
    ).toBeVisible();

    await user.type(
      screen.getByRole('textbox', { name: 'Your entry' }),
      'I noticed how much quieter the afternoon felt.',
    );
    await user.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(repository.createTextEntry).toHaveBeenCalledWith({
        content: 'I noticed how much quieter the afternoon felt.',
      }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith(routes.entries.path));
  });

  it('keeps writing visible while saving and after an error', async () => {
    let rejectCreation: ((error: Error) => void) | undefined;
    const createTextEntry = vi.fn(
      () =>
        new Promise<EntrySummary>((_, reject) => {
          rejectCreation = reject;
        }),
    );
    const user = userEvent.setup();
    renderNewEntry(createRepository({ createTextEntry }));

    const textbox = screen.getByRole('textbox', { name: 'Your entry' });
    await user.type(textbox, 'Keep these words safe.');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText(
        'Saving your words and preparing them for reflection.',
      ),
    ).toBeVisible();
    expect(textbox).toBeDisabled();

    await act(async () => {
      rejectCreation?.(new Error('Unavailable'));
    });

    expect(
      await screen.findByText(/Your entry could not be added/),
    ).toBeVisible();
    expect(textbox).toHaveValue('Keep these words safe.');
  });

  it('warns before unsaved writing is discarded', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = userEvent.setup();
    renderNewEntry();

    await user.type(
      screen.getByRole('textbox', { name: 'Your entry' }),
      'An unfinished thought',
    );

    const unloadEvent = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unloadEvent);
    expect(unloadEvent.defaultPrevented).toBe(true);

    await user.click(screen.getByRole('link', { name: routes.entries.label }));
    expect(confirm).toHaveBeenCalledWith(
      'Leave this entry? Your unsaved changes will be lost.',
    );
  });

  it('explains how to recover when microphone permission is denied', async () => {
    installMicrophone({ denied: true });
    const user = userEvent.setup();
    renderNewEntry();

    await user.click(screen.getByRole('radio', { name: 'Record' }));
    await user.click(screen.getByRole('button', { name: 'Start' }));

    expect(
      await screen.findByText(/Microphone access is blocked/),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled();
  });

  it('records, pauses, stops, and submits a voice entry', async () => {
    const { stopTrack } = installMicrophone();
    const repository = createRepository();
    const user = userEvent.setup();
    renderNewEntry(repository);

    await user.click(screen.getByRole('radio', { name: 'Record' }));
    await user.click(screen.getByRole('button', { name: 'Start' }));
    expect(await screen.findByText('Recording')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Pause' }));
    expect(screen.getByText('Paused')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Resume' }));
    await user.click(screen.getByRole('button', { name: 'Stop' }));

    expect(await screen.findByText('Recording ready')).toBeVisible();
    expect(stopTrack).toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(repository.createVoiceEntry).toHaveBeenCalledWith(
        expect.any(Blob),
      ),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith(routes.entries.path));
  });

  it('keeps mode switching unavailable while a recording is active', async () => {
    installMicrophone();
    const user = userEvent.setup();
    renderNewEntry();

    await user.click(screen.getByRole('radio', { name: 'Record' }));
    await user.click(screen.getByRole('button', { name: 'Start' }));

    const writeMode = screen.getByRole('radio', { name: 'Write' });
    expect(writeMode).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    expect(writeMode).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Record again' }));
    expect(writeMode).toBeEnabled();
  });

  it('keeps a recording available when voice entry creation fails', async () => {
    installMicrophone();
    const user = userEvent.setup();
    renderNewEntry(
      createRepository({
        createVoiceEntry: vi.fn().mockRejectedValue(new Error('Unavailable')),
      }),
    );

    await user.click(screen.getByRole('radio', { name: 'Record' }));
    await user.click(screen.getByRole('button', { name: 'Start' }));
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText(/The voice entry could not be added/),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Add' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Record again' })).toBeEnabled();
  });
});

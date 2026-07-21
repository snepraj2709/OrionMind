'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import {
  Mic,
  Pause,
  PenLine,
  Play,
  RotateCcw,
  Square,
  Trash2,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useRef, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

import { Surface } from '@/components/cards';
import { StatusBadge } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  InlineError,
  ProcessingState,
  SectionLoader,
} from '@/components/feedback';
import {
  FormError,
  FormField,
  SubmitButton,
  TextArea,
} from '@/components/forms';
import { PageHeader, PageShell } from '@/components/layout';
import { Breadcrumbs, SegmentedControl } from '@/components/navigation';
import { routes } from '@/config/routes';

import { useCreateEntryMutation } from './queries';
import {
  entryComposerRepository,
  EntryRequestError,
  type EntryComposerRepository,
} from './repository';
import {
  canonicalizeDraftContent,
  useTextEntryDraft,
} from './use-text-entry-draft';
import { useUnsavedEntryWarning } from './use-unsaved-entry-warning';
import { useVoiceRecorder } from './use-voice-recorder';

const textEntrySchema = z.object({
  content: z
    .string()
    .trim()
    .min(1, 'Write something before adding this entry.')
    .max(10_000, 'Keep this entry under 10,000 characters.'),
});

type TextEntryValues = z.infer<typeof textEntrySchema>;
type EntryMode = 'text' | 'voice';

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, '0')}`;
}

export interface NewEntryScreenProps {
  repository?: EntryComposerRepository;
}

export function NewEntryScreen({
  repository = entryComposerRepository,
}: NewEntryScreenProps) {
  const router = useRouter();
  const [mode, setMode] = useState<EntryMode>('text');
  const [isPreparingTextSubmit, setIsPreparingTextSubmit] = useState(false);
  const voice = useVoiceRecorder();
  const voiceSubmissionRef = useRef<
    | {
        key: string;
        recording: Blob;
      }
    | undefined
  >(undefined);
  const form = useForm<TextEntryValues>({
    resolver: zodResolver(textEntrySchema),
    defaultValues: { content: '' },
  });
  const content = useWatch({ control: form.control, name: 'content' });
  const restoreDraft = useCallback(
    (draftContent: string) => form.reset({ content: draftContent }),
    [form],
  );
  const draft = useTextEntryDraft({
    content,
    onRestore: restoreDraft,
    repository,
  });

  const createEntry = useCreateEntryMutation(repository, (input) => {
    if (input.mode === 'text') {
      draft.markSubmitted();
      form.reset();
    } else {
      voice.reset();
      voiceSubmissionRef.current = undefined;
    }
    router.push(routes.entries.path);
  });

  const hasUnsavedChanges =
    draft.hasUnsavedChanges ||
    ['recording', 'paused', 'ready'].includes(voice.state);
  useUnsavedEntryWarning(hasUnsavedChanges && !createEntry.isSuccess);

  async function submitText(values: TextEntryValues) {
    setIsPreparingTextSubmit(true);
    try {
      const canonicalContent = await draft.flush(values.content);
      await createEntry.mutateAsync({
        mode: 'text',
        content: canonicalContent,
      });
    } catch {
      // Draft and creation state retain safe, user-facing failure details.
    } finally {
      setIsPreparingTextSubmit(false);
    }
  }

  function submitVoice() {
    if (voice.recording) {
      if (voiceSubmissionRef.current?.recording !== voice.recording) {
        voiceSubmissionRef.current = {
          key: crypto.randomUUID(),
          recording: voice.recording,
        };
      }
      createEntry.mutate({
        mode: 'voice',
        idempotencyKey: voiceSubmissionRef.current.key,
        voice: voice.recording,
      });
    }
  }

  async function discardDraft() {
    if (!window.confirm('Discard this saved draft?')) return;
    try {
      await draft.discard();
    } catch {
      // The draft remains visible and the hook exposes the retryable error.
    }
  }

  function changeMode(nextMode: string) {
    createEntry.reset();
    if (voice.state !== 'idle') voice.reset();
    setMode(nextMode as EntryMode);
  }

  function startRecording() {
    createEntry.reset();
    voiceSubmissionRef.current = undefined;
    void voice.start();
  }

  function resetRecording() {
    voiceSubmissionRef.current = undefined;
    voice.reset();
  }

  const textBusy =
    isPreparingTextSubmit || createEntry.isPending || draft.isDiscarding;
  const textUnavailable =
    draft.isRestorePending || draft.isRestoreError || !draft.initialized;
  const voiceError =
    createEntry.error instanceof EntryRequestError &&
    createEntry.error.status === 413
      ? 'The recording is too large. Record a shorter entry and try again.'
      : createEntry.error instanceof EntryRequestError &&
          createEntry.error.status === 415
        ? 'This recording format is not supported. Record again using your browser’s default format.'
        : 'The voice entry could not be added. Your recording is still here—try again when you are ready.';

  return (
    <PageShell className="space-y-8">
      <PageHeader
        breadcrumbs={
          <Breadcrumbs
            items={[
              { href: routes.entries.path, label: routes.entries.label },
              { label: routes.newEntry.label },
            ]}
          />
        }
        description="Capture what is present without needing to organize it first."
        title={routes.newEntry.label}
      />

      <SegmentedControl
        ariaLabel="Entry mode"
        items={[
          {
            disabled:
              createEntry.isPending ||
              (mode === 'voice' && voice.state !== 'idle'),
            icon: <PenLine aria-hidden="true" className="size-4" />,
            label: 'Write',
            value: 'text',
          },
          {
            disabled: createEntry.isPending,
            icon: <Mic aria-hidden="true" className="size-4" />,
            label: 'Record',
            value: 'voice',
          },
        ]}
        onValueChange={changeMode}
        value={mode}
      />

      {mode === 'text' ? (
        <form
          className="text-measure-wide space-y-6"
          onSubmit={form.handleSubmit(submitText)}
        >
          <FormField
            description={`${content.length.toLocaleString()} of 10,000 characters`}
            error={form.formState.errors.content?.message}
            id="entry-content"
            label="Your entry"
            required
          >
            <TextArea
              className="field-sizing-fixed resize-y"
              disabled={textBusy || textUnavailable}
              placeholder="Begin wherever you are…"
              rows={14}
              {...form.register('content')}
            />
          </FormField>
          {draft.isRestorePending ? (
            <SectionLoader label="Restoring saved draft" />
          ) : null}
          {draft.isRestoreError ? (
            <InlineError
              action={
                <AppButton
                  onClick={draft.retryRestore}
                  size="compact"
                  variant="outline"
                >
                  Retry
                </AppButton>
              }
            >
              Your saved draft could not be restored.
            </InlineError>
          ) : null}
          {draft.saveStatus === 'error' ? (
            <InlineError
              action={
                <AppButton
                  onClick={() => {
                    void draft.flush(content).catch(() => undefined);
                  }}
                  size="compact"
                  variant="outline"
                >
                  Retry
                </AppButton>
              }
            >
              Your draft could not be synchronized. Your writing is still here.
            </InlineError>
          ) : null}
          {draft.saveStatus === 'saving' && !isPreparingTextSubmit ? (
            <Typography
              className="text-muted-foreground"
              role="status"
              variant="bodySmall"
            >
              Saving draft…
            </Typography>
          ) : null}
          {draft.saveStatus === 'saved' && !isPreparingTextSubmit ? (
            <Typography
              className="text-muted-foreground"
              role="status"
              variant="bodySmall"
            >
              Draft saved
            </Typography>
          ) : null}
          {createEntry.isError ? (
            <FormError>
              Your entry could not be added. Retry after sometime.
            </FormError>
          ) : null}
          {isPreparingTextSubmit || createEntry.isPending ? (
            <ProcessingState description="Saving your words and preparing them for reflection." />
          ) : null}
          <div className="flex flex-wrap gap-3">
            <SubmitButton
              disabled={textUnavailable || draft.isDiscarding}
              loading={isPreparingTextSubmit || createEntry.isPending}
              loadingLabel="Adding entry"
            >
              Add
            </SubmitButton>
            {canonicalizeDraftContent(content) || draft.hasServerDraft ? (
              <AppButton
                disabled={textBusy || textUnavailable}
                leftIcon={<Trash2 aria-hidden="true" />}
                loading={draft.isDiscarding}
                loadingLabel="Discarding draft"
                onClick={() => void discardDraft()}
                type="button"
                variant="rejectOutline"
              >
                Discard draft
              </AppButton>
            ) : null}
          </div>
        </form>
      ) : (
        <div className="text-measure-wide space-y-6">
          <Surface className="items-center gap-6 p-8 text-center">
            <div className="bg-secondary text-primary radius-pill flex size-16 items-center justify-center">
              <Mic aria-hidden="true" className="size-6" />
            </div>

            {voice.state === 'idle' ? (
              <div className="space-y-2">
                <Typography className="text-muted-foreground" variant="body">
                  Speak naturally, transcription and processesing begin when you
                  finish.
                </Typography>
              </div>
            ) : null}

            {voice.state === 'requesting' ? (
              <SectionLoader label="Requesting microphone access" />
            ) : null}

            {voice.state === 'recording' || voice.state === 'paused' ? (
              <div aria-live="polite" className="space-y-4">
                <StatusBadge
                  icon={<Mic aria-hidden="true" />}
                  label={voice.state === 'paused' ? 'Paused' : 'Recording'}
                  variant={voice.state === 'paused' ? 'neutral' : 'processing'}
                />
                <Typography variant="display">
                  {formatDuration(voice.elapsedSeconds)}
                </Typography>
              </div>
            ) : null}

            {voice.state === 'ready' ? (
              <div className="space-y-2">
                <Typography as="h2" variant="componentTitle">
                  Recording ready
                </Typography>
                <Typography className="text-muted-foreground" variant="body">
                  Add the entry to begin transcription and reflection.
                </Typography>
              </div>
            ) : null}

            {voice.state === 'permission-denied' ? (
              <InlineError>
                Microphone access is blocked. Allow access in your browser, then
                try again.
              </InlineError>
            ) : null}

            {voice.state === 'failed' || createEntry.isError ? (
              <InlineError>
                {createEntry.isError
                  ? voiceError
                  : 'The recording could not be prepared. Your journal has not been changed.'}
              </InlineError>
            ) : null}

            {createEntry.isPending ? (
              <ProcessingState description="Uploading and preparing your voice entry for transcription." />
            ) : null}

            <div className="flex flex-wrap justify-center gap-3">
              {['idle', 'permission-denied', 'failed'].includes(voice.state) ? (
                <AppButton
                  leftIcon={<Mic aria-hidden="true" />}
                  onClick={startRecording}
                >
                  Start
                </AppButton>
              ) : null}
              {voice.state === 'recording' ? (
                <>
                  <AppButton
                    leftIcon={<Pause aria-hidden="true" />}
                    onClick={voice.pause}
                    variant="secondary"
                  >
                    Pause
                  </AppButton>
                  <AppButton
                    leftIcon={<Square aria-hidden="true" />}
                    onClick={voice.stop}
                  >
                    Stop
                  </AppButton>
                </>
              ) : null}
              {voice.state === 'paused' ? (
                <>
                  <AppButton
                    leftIcon={<Play aria-hidden="true" />}
                    onClick={voice.resume}
                    variant="secondary"
                  >
                    Resume
                  </AppButton>
                  <AppButton
                    leftIcon={<Square aria-hidden="true" />}
                    onClick={voice.stop}
                  >
                    Stop
                  </AppButton>
                </>
              ) : null}
              {voice.state === 'ready' ? (
                <>
                  <AppButton
                    disabled={createEntry.isPending}
                    leftIcon={<RotateCcw aria-hidden="true" />}
                    onClick={resetRecording}
                    variant="secondary"
                  >
                    Record again
                  </AppButton>
                  <AppButton
                    loading={createEntry.isPending}
                    loadingLabel="Adding voice entry"
                    onClick={submitVoice}
                  >
                    Add
                  </AppButton>
                </>
              ) : null}
            </div>

            {/* <Typography className="text-muted-foreground" variant="bodySmall">
              Audio is deleted after transcription.
            </Typography> */}
          </Surface>
        </div>
      )}
    </PageShell>
  );
}

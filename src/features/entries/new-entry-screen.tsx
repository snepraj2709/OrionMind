'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Mic, Pause, PenLine, Play, RotateCcw, Square } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
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

import { entriesRepository } from './mock-repository';
import { useCreateEntryMutation } from './queries';
import type { EntriesRepository } from './repository';
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
  repository?: EntriesRepository;
}

export function NewEntryScreen({
  repository = entriesRepository,
}: NewEntryScreenProps) {
  const router = useRouter();
  const [mode, setMode] = useState<EntryMode>('text');
  const voice = useVoiceRecorder();
  const form = useForm<TextEntryValues>({
    resolver: zodResolver(textEntrySchema),
    defaultValues: { content: '' },
  });
  const content = useWatch({ control: form.control, name: 'content' });

  const createEntry = useCreateEntryMutation(repository, () => {
    form.reset();
    voice.reset();
    router.push(routes.entries.path);
  });

  const hasUnsavedChanges =
    content.trim().length > 0 ||
    ['recording', 'paused', 'ready'].includes(voice.state);
  useUnsavedEntryWarning(hasUnsavedChanges && !createEntry.isSuccess);

  function submitText(values: TextEntryValues) {
    createEntry.mutate({ mode: 'text', content: values.content });
  }

  function submitVoice() {
    if (voice.recording) {
      createEntry.mutate({ mode: 'voice', voice: voice.recording });
    }
  }

  function changeMode(nextMode: string) {
    createEntry.reset();
    if (voice.state !== 'idle') voice.reset();
    setMode(nextMode as EntryMode);
  }

  function startRecording() {
    createEntry.reset();
    void voice.start();
  }

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
              disabled={createEntry.isPending}
              placeholder="Begin wherever you are…"
              rows={14}
              {...form.register('content')}
            />
          </FormField>
          {createEntry.isError ? (
            <FormError>
              Your entry could not be added. Retry after sometime.
            </FormError>
          ) : null}
          {createEntry.isPending ? (
            <ProcessingState description="Saving your words and preparing them for reflection." />
          ) : null}
          <SubmitButton
            loading={createEntry.isPending}
            loadingLabel="Adding entry"
          >
            Add
          </SubmitButton>
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
                  ? 'The voice entry could not be added. Your recording is still here—try again when you are ready.'
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
                    onClick={voice.reset}
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

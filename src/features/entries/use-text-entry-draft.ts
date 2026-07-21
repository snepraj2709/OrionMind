'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import { entryKeys } from './query-keys';
import type { EntryComposerRepository } from './repository';

export const DRAFT_AUTOSAVE_DELAY_MS = 750;

export type DraftSaveStatus = 'idle' | 'saving' | 'saved' | 'error';

interface UseTextEntryDraftOptions {
  content: string;
  onRestore: (content: string) => void;
  repository: EntryComposerRepository;
}

export function canonicalizeDraftContent(content: string) {
  return content
    .replace(/\r\n?/g, '\n')
    .normalize('NFC')
    .replace(/^[\t\n\v\f\r ]+|[\t\n\v\f\r ]+$/g, '');
}

export function useTextEntryDraft({
  content,
  onRestore,
  repository,
}: UseTextEntryDraftOptions) {
  const queryClient = useQueryClient();
  const draftQuery = useQuery({
    queryKey: entryKeys.draft,
    queryFn: () => repository.getTextDraft(),
    retry: false,
  });
  const [initialized, setInitialized] = useState(false);
  const [savedContent, setSavedContentState] = useState<string>();
  const [saveStatus, setSaveStatus] = useState<DraftSaveStatus>('idle');
  const [isDiscarding, setIsDiscarding] = useState(false);
  const canonicalContent = canonicalizeDraftContent(content);
  const contentRef = useRef(canonicalContent);
  const savedContentRef = useRef<string | undefined>(undefined);
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());
  const saveTimerRef = useRef<number | undefined>(undefined);
  const latestSaveRef = useRef(0);

  useEffect(() => {
    contentRef.current = canonicalContent;
  }, [canonicalContent]);

  const setSavedContent = useCallback((nextContent: string) => {
    savedContentRef.current = nextContent;
    setSavedContentState(nextContent);
  }, []);

  useEffect(() => {
    if (initialized || !draftQuery.isSuccess) return;
    const timer = window.setTimeout(() => {
      const restoredContent = draftQuery.data.content ?? '';
      onRestore(restoredContent);
      setSavedContent(restoredContent);
      setSaveStatus(restoredContent ? 'saved' : 'idle');
      setInitialized(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    draftQuery.data,
    draftQuery.isSuccess,
    initialized,
    onRestore,
    setSavedContent,
  ]);

  const enqueueSave = useCallback(
    async (nextContent: string) => {
      const canonicalContent = canonicalizeDraftContent(nextContent);
      const saveId = ++latestSaveRef.current;
      setSaveStatus('saving');
      const operation = saveChainRef.current.then(() =>
        repository.saveTextDraft(canonicalContent),
      );
      saveChainRef.current = operation.then(
        () => undefined,
        () => undefined,
      );
      try {
        const saved = await operation;
        const confirmedContent = saved.content ?? '';
        setSavedContent(confirmedContent);
        if (saveId === latestSaveRef.current) {
          setSaveStatus(
            contentRef.current === confirmedContent ? 'saved' : 'idle',
          );
        }
        return confirmedContent;
      } catch (error) {
        if (saveId === latestSaveRef.current) setSaveStatus('error');
        throw error;
      }
    },
    [repository, setSavedContent],
  );

  useEffect(() => {
    if (!initialized || isDiscarding) return;
    const canonicalContent = canonicalizeDraftContent(content);
    if (canonicalContent === savedContentRef.current) return;
    if (saveTimerRef.current !== undefined) {
      window.clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = undefined;
      void enqueueSave(canonicalContent).catch(() => undefined);
    }, DRAFT_AUTOSAVE_DELAY_MS);
    return () => {
      if (saveTimerRef.current !== undefined) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = undefined;
      }
    };
  }, [content, enqueueSave, initialized, isDiscarding]);

  const flush = useCallback(
    async (nextContent: string) => {
      if (saveTimerRef.current !== undefined) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = undefined;
      }
      await saveChainRef.current;
      const canonicalContent = canonicalizeDraftContent(nextContent);
      if (canonicalContent !== savedContentRef.current) {
        await enqueueSave(canonicalContent);
      }
      return canonicalContent;
    },
    [enqueueSave],
  );

  const discard = useCallback(async () => {
    if (saveTimerRef.current !== undefined) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = undefined;
    }
    setIsDiscarding(true);
    setSaveStatus('saving');
    await saveChainRef.current;
    try {
      const discarded = await repository.discardTextDraft();
      const nextContent = discarded.content ?? '';
      setSavedContent(nextContent);
      onRestore(nextContent);
      setSaveStatus('idle');
      queryClient.setQueryData(entryKeys.draft, discarded);
    } catch (error) {
      setSaveStatus('error');
      throw error;
    } finally {
      setIsDiscarding(false);
    }
  }, [onRestore, queryClient, repository, setSavedContent]);

  const markSubmitted = useCallback(() => {
    if (saveTimerRef.current !== undefined) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = undefined;
    }
    latestSaveRef.current += 1;
    setSavedContent('');
    setSaveStatus('idle');
    queryClient.setQueryData(entryKeys.draft, {
      content: null,
      updatedAt: null,
    });
  }, [queryClient, setSavedContent]);

  const retryRestore = useCallback(() => {
    void draftQuery.refetch();
  }, [draftQuery]);

  return {
    discard,
    flush,
    hasServerDraft: Boolean(savedContent),
    hasUnsavedChanges: initialized && canonicalContent !== savedContent,
    initialized,
    isDiscarding,
    isRestoreError: draftQuery.isError,
    isRestorePending: draftQuery.isPending,
    markSubmitted,
    retryRestore,
    saveStatus,
  };
}

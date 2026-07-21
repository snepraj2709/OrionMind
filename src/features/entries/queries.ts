'use client';

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';

import { entriesRepository } from './mock-repository';
import type { EntriesQuery } from './model';
import { entryKeys } from './query-keys';
import { entryComposerRepository, entriesListRepository } from './repository';
import type {
  EntryComposerRepository,
  EntriesListRepository,
  CreateEntryInput,
  EntriesRepository,
  ExtractedItemDecisionInput,
} from './repository';

export function useEntriesQuery(
  queryInput: EntriesQuery,
  repository: EntriesListRepository = entriesListRepository,
) {
  const query = useQuery({
    queryKey: entryKeys.list(queryInput),
    queryFn: () => repository.listEntries(queryInput),
    placeholderData: keepPreviousData,
  });

  return {
    query,
    viewStatus: getDataViewStatus({
      hasData: query.data !== undefined,
      isError: query.isError,
      isFetching: query.isFetching,
      isPending: query.isPending,
    }),
  };
}

export function useEntryQuery(
  entryId: string,
  repository: EntriesRepository = entriesRepository,
) {
  const query = useQuery({
    queryKey: entryKeys.detail(entryId),
    queryFn: () => repository.getEntry(entryId),
  });

  return {
    query,
    viewStatus: getDataViewStatus({
      hasData: query.data !== undefined,
      isError: query.isError,
      isFetching: query.isFetching,
      isPending: query.isPending,
    }),
  };
}

export function useCreateEntryMutation(
  repository: EntryComposerRepository = entryComposerRepository,
  onSuccess?: (input: CreateEntryInput) => void | Promise<void>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateEntryInput) =>
      input.mode === 'text'
        ? repository.createTextEntry({ content: input.content ?? '' })
        : repository.createVoiceEntry({
            idempotencyKey: input.idempotencyKey ?? '',
            recording: input.voice ?? new Blob(),
          }),
    onSuccess: async (_entry, input) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: entryKeys.lists }),
        queryClient.invalidateQueries({ queryKey: entryKeys.draft }),
      ]);
      await onSuccess?.(input);
    },
  });
}

export function useEntryDecisionMutation(
  repository: EntriesRepository = entriesRepository,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ExtractedItemDecisionInput) =>
      repository.decideExtractedItem(input),
    onSuccess: (entry, input) => {
      queryClient.setQueryData(entryKeys.detail(entry.id), entry);
      void queryClient.invalidateQueries({ queryKey: entryKeys.lists });
      void queryClient.invalidateQueries({ queryKey: ['approvals'] });
      void queryClient.invalidateQueries({ queryKey: ['saved-items'] });
      if (input.kind === 'reflection' && input.status === 'approved') {
        void queryClient.invalidateQueries({
          queryKey: ['reflections'],
          refetchType: 'none',
        });
      }
    },
  });
}

export function useRetryEntryMutation(
  entryId: string,
  repository: EntriesRepository = entriesRepository,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => repository.retryEntry(entryId),
    onSuccess: (entry) => {
      queryClient.setQueryData(entryKeys.detail(entry.id), entry);
      void queryClient.invalidateQueries({ queryKey: entryKeys.lists });
    },
  });
}

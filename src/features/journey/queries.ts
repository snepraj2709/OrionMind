'use client';

import { useQuery } from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';

import { journeyRepository } from './repository';
import type { JourneyRange } from './model';
import type { JourneyRepository } from './repository';

export function useJourneyEntriesQuery(
  range: JourneyRange,
  userId: string | undefined,
  repository: JourneyRepository = journeyRepository,
) {
  const journeyQuery = useQuery({
    enabled: userId !== undefined,
    queryKey: ['journey', userId, range],
    queryFn: () => {
      if (!userId) throw new Error('An authenticated user is required.');
      return repository.getJourney(range, userId);
    },
  });
  const statusQuery = useQuery({
    enabled: userId !== undefined,
    queryKey: ['journey', 'status', userId],
    queryFn: () => {
      if (!userId) throw new Error('An authenticated user is required.');
      return repository.getJourneyStatus(userId);
    },
  });

  return {
    journeyQuery,
    statusQuery,
    viewStatus: getDataViewStatus({
      hasData:
        journeyQuery.data !== undefined && statusQuery.data !== undefined,
      isError: journeyQuery.isError || statusQuery.isError,
      isFetching: journeyQuery.isFetching || statusQuery.isFetching,
      isPending: journeyQuery.isPending || statusQuery.isPending,
    }),
  };
}

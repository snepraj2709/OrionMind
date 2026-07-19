'use client';

import { useQuery } from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';

import { journeyRepository } from './mock-repository';
import type { JourneyRange } from './model';
import type { JourneyRepository } from './repository';

export function useJourneyEntriesQuery(
  range: JourneyRange,
  repository: JourneyRepository = journeyRepository,
) {
  const query = useQuery({
    queryKey: ['journey', range],
    queryFn: () => repository.getJourneyEntries(range),
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

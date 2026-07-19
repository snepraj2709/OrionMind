'use client';

import { useQuery } from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';

import { reflectionsRepository } from './mock-repository';
import type { ReflectionRange } from './model';
import type { ReflectionsRepository } from './repository';

export function useReflectionEntriesQuery(
  range: ReflectionRange,
  repository: ReflectionsRepository = reflectionsRepository,
) {
  const query = useQuery({
    queryKey: ['reflections', range],
    queryFn: () => repository.getReflectionEntries(range),
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

'use client';

import { useQuery } from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';

import type { ReflectionRequest } from './api-schema';
import {
  reflectionsRepository,
  type ReflectionsRepository,
} from './repository';

export function useReflectionQuery(
  input: ReflectionRequest | undefined,
  repository: ReflectionsRepository = reflectionsRepository,
) {
  const query = useQuery({
    enabled: input !== undefined,
    queryKey: [
      'reflections',
      input?.userId,
      input?.reflectionTab,
      input?.range,
    ],
    queryFn: () => {
      if (!input) throw new Error('An authenticated user is required.');
      return repository.getReflection(input);
    },
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

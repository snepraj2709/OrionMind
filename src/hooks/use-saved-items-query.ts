'use client';

import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';
import {
  savedItemsRepository,
  type SavedItemsQuery,
  type SavedItemsRepository,
} from '@/services/saved-items';

export function useSavedItemsQuery(
  queryInput: SavedItemsQuery,
  repository: SavedItemsRepository = savedItemsRepository,
) {
  const query = useQuery({
    queryKey: ['saved-items', queryInput],
    queryFn: () => repository.listSavedItems(queryInput),
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

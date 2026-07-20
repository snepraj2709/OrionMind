'use client';

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { entryKeys } from '@/features/entries';
import { getDataViewStatus } from '@/lib/query-state';

import { approvalsRepository } from './mock-repository';
import type { ApprovalsQuery } from './model';
import type { ApprovalsRepository } from './repository';

export function useApprovalsQuery(
  queryInput: ApprovalsQuery,
  repository: ApprovalsRepository = approvalsRepository,
) {
  const query = useQuery({
    queryKey: ['approvals', queryInput],
    queryFn: () => repository.listPendingApprovals(queryInput),
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

export function usePendingApprovalCount(initialCount = 0) {
  const { query } = useApprovalsQuery({
    kind: 'all',
    pageIndex: 0,
    pageSize: 1,
    search: '',
    status: 'all',
    theme: 'all',
  });

  return query.data?.totalAll ?? initialCount;
}

export function useApprovalDecisionMutation(
  repository: ApprovalsRepository = approvalsRepository,
  onSuccess?: (
    item: Awaited<ReturnType<ApprovalsRepository['decideApproval']>>,
  ) => void | Promise<void>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: Parameters<ApprovalsRepository['decideApproval']>[0]) =>
      repository.decideApproval(input),
    onSuccess: async (item) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['approvals'] }),
        queryClient.invalidateQueries({ queryKey: ['saved-items'] }),
        queryClient.invalidateQueries({
          queryKey: entryKeys.detail(item.entryId),
        }),
        queryClient.invalidateQueries({ queryKey: entryKeys.lists }),
        ...(item.kind === 'reflection' && item.status === 'approved'
          ? [
              queryClient.invalidateQueries({
                queryKey: ['reflections'],
                refetchType: 'none',
              }),
            ]
          : []),
      ]);
      await onSuccess?.(item);
    },
  });
}

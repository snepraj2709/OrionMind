'use client';

import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';

import type { ReviewItem, ReviewListQuery, ReviewScope } from './model';
import {
  reviewRepository,
  type ReviewRepository,
  type SubmitReviewFeedbackInput,
} from './repository';

export const reviewKeys = {
  user: (userId: string) => ['review', userId] as const,
  list: (userId: string, query: ReviewListQuery) =>
    [
      'review',
      userId,
      'list',
      query.scope,
      query.category,
      query.status,
      query.page,
      query.page_size,
    ] as const,
};

export function useReviewItemsQuery(
  userId: string | undefined,
  input: ReviewListQuery,
  repository: ReviewRepository = reviewRepository,
) {
  const query = useQuery({
    enabled: userId !== undefined,
    queryKey: reviewKeys.list(userId ?? 'unauthenticated', input),
    queryFn: ({ signal }) => {
      if (!userId) throw new Error('An authenticated user is required.');
      return repository.listItems(input, signal);
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

const pendingScopes = [
  'entry_insight',
  'pattern',
] as const satisfies readonly ReviewScope[];

export function usePendingReviewCount(
  userId: string | undefined,
  repository: ReviewRepository = reviewRepository,
) {
  const queries = useQueries({
    queries: pendingScopes.map((scope) => {
      const input: ReviewListQuery = {
        scope,
        category: 'all',
        status: 'pending',
        page: 1,
        page_size: 1,
      };
      return {
        enabled: userId !== undefined,
        queryKey: reviewKeys.list(userId ?? 'unauthenticated', input),
        queryFn: ({ signal }: { signal: AbortSignal }) => {
          if (!userId) throw new Error('An authenticated user is required.');
          return repository.listItems(input, signal);
        },
      };
    }),
  });
  const hasEveryCount = queries.every((query) => query.data !== undefined);
  const isError = queries.some((query) => query.isError);

  return {
    count:
      hasEveryCount && !isError
        ? queries.reduce(
            (total, query) => total + (query.data?.pagination.total ?? 0),
            0,
          )
        : undefined,
    isError,
  };
}

export function useReviewFeedbackMutation(
  userId: string | undefined,
  repository: ReviewRepository = reviewRepository,
  onSuccess?: (item: ReviewItem) => void | Promise<void>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: SubmitReviewFeedbackInput) =>
      repository.submitFeedback(input),
    onError: async () => {
      if (userId) {
        await queryClient.invalidateQueries({
          queryKey: reviewKeys.user(userId),
        });
      }
      await queryClient.invalidateQueries({
        queryKey: ['reflections'],
        refetchType: 'none',
      });
    },
    onSuccess: async (item) => {
      if (userId) {
        await queryClient.invalidateQueries({
          queryKey: reviewKeys.user(userId),
        });
      }
      await queryClient.invalidateQueries({
        queryKey: ['reflections'],
        refetchType: 'none',
      });
      await onSuccess?.(item);
    },
  });
}

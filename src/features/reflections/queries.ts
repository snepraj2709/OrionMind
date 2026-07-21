'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getDataViewStatus } from '@/lib/query-state';

import type {
  ReflectionApiResponse,
  ReflectionFeedbackResponse,
  ReflectionRange,
  ReflectionRequest,
} from './api-schema';
import {
  reflectionsRepository,
  type ReflectionsRepository,
} from './repository';

export const reflectionKeys = {
  all: ['reflections'] as const,
  range: (userId: string, range: ReflectionRange) =>
    ['reflections', userId, range] as const,
};

export function useReflectionQuery(
  userId: string | undefined,
  input: ReflectionRequest,
  repository: ReflectionsRepository = reflectionsRepository,
) {
  const query = useQuery({
    enabled: userId !== undefined,
    queryKey: reflectionKeys.range(userId ?? 'unauthenticated', input.range),
    queryFn: () => {
      if (!userId) throw new Error('An authenticated user is required.');
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

function withInsightFeedback(
  aggregate: ReflectionApiResponse,
  insightId: string,
  feedback: ReflectionFeedbackResponse | null,
): ReflectionApiResponse {
  const hiddenDriver = aggregate.data.hiddenDriver;
  const recurringLoop = aggregate.data.recurringLoop;
  const innerTensions = aggregate.data.innerTensions;

  return {
    ...aggregate,
    data: {
      hiddenDriver:
        hiddenDriver.status === 'available' && hiddenDriver.id === insightId
          ? { ...hiddenDriver, feedback }
          : hiddenDriver,
      recurringLoop:
        recurringLoop.status === 'available' && recurringLoop.id === insightId
          ? { ...recurringLoop, feedback }
          : recurringLoop,
      innerTensions:
        innerTensions.status === 'available'
          ? {
              ...innerTensions,
              tensions: innerTensions.tensions.map((tension) =>
                tension.id === insightId ? { ...tension, feedback } : tension,
              ),
            }
          : innerTensions,
    },
  };
}

interface SubmitFeedbackInput {
  snapshotId: string;
  insightId: string;
  response: ReflectionFeedbackResponse;
}

type ReflectionQueryKey = ReturnType<typeof reflectionKeys.range>;

interface FeedbackMutationInput extends SubmitFeedbackInput {
  queryKey: ReflectionQueryKey;
  scope: string;
}

interface FeedbackMutationContext {
  insightId: string;
  previous: ReflectionApiResponse | undefined;
}

export function useReflectionFeedbackMutation(
  userId: string | undefined,
  range: ReflectionRange,
  repository: ReflectionsRepository = reflectionsRepository,
) {
  const queryClient = useQueryClient();
  const pendingRef = useRef(new Set<string>());
  const [pendingInsightIds, setPendingInsightIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [scopedErrors, setScopedErrors] = useState<Record<string, string>>({});
  const queryKey = reflectionKeys.range(userId ?? 'unauthenticated', range);
  const scope = queryKey.join(':');

  function errorKey(insightId: string, mutationScope = scope) {
    return `${mutationScope}:${insightId}`;
  }

  const mutation = useMutation({
    mutationFn: (input: FeedbackMutationInput) =>
      repository.putFeedback({
        insightId: input.insightId,
        response: input.response,
        snapshotId: input.snapshotId,
      }),
    onMutate: async (input): Promise<FeedbackMutationContext> => {
      await queryClient.cancelQueries({
        queryKey: input.queryKey,
        exact: true,
      });
      const previous = queryClient.getQueryData<ReflectionApiResponse>(
        input.queryKey,
      );
      queryClient.setQueryData<ReflectionApiResponse>(
        input.queryKey,
        (current) =>
          current
            ? withInsightFeedback(current, input.insightId, input.response)
            : current,
      );
      setScopedErrors((current) => {
        const next = { ...current };
        delete next[errorKey(input.insightId, input.scope)];
        return next;
      });
      return { insightId: input.insightId, previous };
    },
    onError: (_error, input, context) => {
      const previousFeedback = context?.previous
        ? findInsightFeedback(context.previous, input.insightId)
        : undefined;
      queryClient.setQueryData<ReflectionApiResponse>(
        input.queryKey,
        (current) =>
          current && previousFeedback !== undefined
            ? withInsightFeedback(current, input.insightId, previousFeedback)
            : context?.previous,
      );
      setScopedErrors((current) => ({
        ...current,
        [errorKey(input.insightId, input.scope)]:
          'Your feedback could not be saved. Please try again.',
      }));
    },
    onSuccess: (result, input) => {
      queryClient.setQueryData<ReflectionApiResponse>(
        input.queryKey,
        (current) =>
          current
            ? withInsightFeedback(current, result.insightId, result.response)
            : current,
      );
      setScopedErrors((current) => {
        const next = { ...current };
        delete next[errorKey(result.insightId, input.scope)];
        return next;
      });
      void queryClient.invalidateQueries({
        queryKey: input.queryKey,
        exact: true,
      });
    },
    onSettled: (_data, _error, input) => {
      pendingRef.current.delete(input.insightId);
      setPendingInsightIds(new Set(pendingRef.current));
    },
  });

  const submitFeedback = useCallback(
    (input: SubmitFeedbackInput) => {
      if (pendingRef.current.has(input.insightId)) return;
      pendingRef.current.add(input.insightId);
      setPendingInsightIds(new Set(pendingRef.current));
      mutation.mutate({ ...input, queryKey, scope });
    },
    [mutation, queryKey, scope],
  );

  const errors = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(scopedErrors)
          .filter(([key]) => key.startsWith(`${scope}:`))
          .map(([key, message]) => [key.slice(scope.length + 1), message]),
      ),
    [scope, scopedErrors],
  );

  return { errors, pendingInsightIds, submitFeedback };
}

function findInsightFeedback(
  aggregate: ReflectionApiResponse,
  insightId: string,
): ReflectionFeedbackResponse | null | undefined {
  if (
    aggregate.data.hiddenDriver.status === 'available' &&
    aggregate.data.hiddenDriver.id === insightId
  ) {
    return aggregate.data.hiddenDriver.feedback;
  }
  if (
    aggregate.data.recurringLoop.status === 'available' &&
    aggregate.data.recurringLoop.id === insightId
  ) {
    return aggregate.data.recurringLoop.feedback;
  }
  if (aggregate.data.innerTensions.status === 'available') {
    return aggregate.data.innerTensions.tensions.find(
      (tension) => tension.id === insightId,
    )?.feedback;
  }
  return undefined;
}

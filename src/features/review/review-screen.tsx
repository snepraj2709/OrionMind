'use client';

import { BookOpenText, Waypoints } from 'lucide-react';
import { type ReactNode, useEffect, useState } from 'react';

import { PaginationControls } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import { DataViewStatus, EmptyState, InlineError } from '@/components/feedback';
import { PageHeader, PageShell } from '@/components/layout';
import { AppLink, SegmentedControl } from '@/components/navigation';
import { dataViewMessages } from '@/config/messages';
import { routes } from '@/config/routes';
import { useAuth } from '@/features/auth';
import { useOnlineStatus } from '@/hooks';

import { reviewPageSizeDefault } from './api-schema';
import type { ReviewListQuery, ReviewScope } from './model';
import { useReviewFeedbackMutation, useReviewItemsQuery } from './queries';
import {
  ReviewRequestError,
  reviewRepository,
  type ReviewRepository,
} from './repository';
import { ReviewQueueItem } from './review-queue-item';

const scopeItems = [
  {
    icon: <BookOpenText aria-hidden="true" className="size-5" />,
    label: 'Entry Insights',
    value: 'entry_insight',
  },
  {
    icon: <Waypoints aria-hidden="true" className="size-5" />,
    label: 'Patterns',
    value: 'pattern',
  },
] satisfies Array<{
  icon: ReactNode;
  label: string;
  value: ReviewScope;
}>;

export interface ReviewScreenProps {
  repository?: ReviewRepository;
}

export function ReviewScreen({
  repository = reviewRepository,
}: ReviewScreenProps) {
  const { user } = useAuth();
  const isOnline = useOnlineStatus();
  const [scope, setScope] = useState<ReviewScope>('entry_insight');
  const [page, setPage] = useState(1);
  const [announcement, setAnnouncement] = useState('');
  const queryInput: ReviewListQuery = {
    scope,
    category: 'all',
    status: 'pending',
    page,
    page_size: reviewPageSizeDefault,
  };
  const { query, viewStatus } = useReviewItemsQuery(
    user?.id,
    queryInput,
    repository,
  );
  const feedback = useReviewFeedbackMutation(user?.id, repository, (item) => {
    setAnnouncement('Feedback saved. Your Review queue is up to date.');
    setPage(1);
    if (item.feedback?.correctedStatement) {
      setAnnouncement(
        'Feedback and corrected statement saved. Your Review queue is up to date.',
      );
    }
  });
  const pageCount = query.data
    ? Math.ceil(query.data.pagination.total / query.data.pagination.pageSize)
    : 0;
  const interactionDisabled =
    !isOnline || query.isFetching || query.isError || feedback.isPending;
  const scopeLabel = scope === 'entry_insight' ? 'Entry Insights' : 'Patterns';
  const feedbackSavedWithoutRecalculation =
    feedback.error instanceof ReviewRequestError &&
    feedback.error.errorCode === 'REFLECTION_RECALCULATION_UNAVAILABLE';
  const failedFeedbackItem = query.data?.items.find(
    (item) => item.id === feedback.variables?.itemId,
  );

  useEffect(() => {
    if (
      query.data &&
      !query.isFetching &&
      query.data.items.length === 0 &&
      page > Math.max(1, pageCount)
    ) {
      const timer = window.setTimeout(() => setPage(Math.max(1, pageCount)), 0);
      return () => window.clearTimeout(timer);
    }
  }, [page, pageCount, query.data, query.isFetching]);

  return (
    <PageShell className="space-y-8">
      <PageHeader
        description="Confirm, refine, or reject the insights Orion may use in your reflections."
        title={routes.review.label}
      />

      <SegmentedControl
        ariaLabel="Review scope"
        items={scopeItems.map((item) => ({
          ...item,
          disabled: interactionDisabled,
        }))}
        onValueChange={(value) => {
          setScope(value as ReviewScope);
          setPage(1);
        }}
        value={scope}
      />

      {!isOnline ? (
        <InlineError>
          You are offline. Loaded Review items remain visible, but feedback is
          disabled until the connection returns.
        </InlineError>
      ) : null}

      {feedback.isError ? (
        <InlineError
          action={
            feedbackSavedWithoutRecalculation ||
            !failedFeedbackItem ? undefined : (
              <AppButton
                aria-label={`Retry feedback for: ${failedFeedbackItem.statement}`}
                disabled={!isOnline || feedback.isPending || query.isError}
                onClick={() => {
                  if (feedback.variables) feedback.mutate(feedback.variables);
                }}
                size="compact"
                variant="ghost"
              >
                Retry
              </AppButton>
            )
          }
        >
          {feedbackSavedWithoutRecalculation
            ? 'Your feedback was saved, but Reflection recalculation could not be scheduled. If the item is still visible, refresh the Review queue.'
            : 'Orion could not confirm whether your feedback was saved. Check the refreshed Review queue before trying again.'}
        </InlineError>
      ) : null}

      <Typography aria-live="polite" className="sr-only" variant="bodySmall">
        {announcement}
      </Typography>

      <DataViewStatus
        initialError={dataViewMessages.review.initial}
        onRetry={() => void query.refetch()}
        refreshError={dataViewMessages.review.refresh}
        refreshingLabel="Refreshing Review items…"
        status={viewStatus}
      />

      {query.data?.pagination.total === 0 ? (
        <EmptyState
          action={
            <AppButton asChild variant="secondary">
              <AppLink href={routes.entries.path}>Return to entries</AppLink>
            </AppButton>
          }
          description={
            scope === 'entry_insight'
              ? 'New supported insights will appear after Orion processes your entries.'
              : 'Supported patterns will appear after Orion builds a reflection.'
          }
          title={`No ${scopeLabel} need review`}
        />
      ) : null}

      {query.data && query.data.items.length > 0 ? (
        <div className="space-y-6">
          <ul aria-live="polite" className="space-y-4">
            {query.data.items.map((item) => (
              <ReviewQueueItem
                disabled={interactionDisabled}
                item={item}
                key={`${item.id}:${item.feedback?.updatedAt ?? 'pending'}`}
                loadingVerdict={
                  feedback.isPending && feedback.variables?.itemId === item.id
                    ? feedback.variables.feedback.verdict
                    : undefined
                }
                onFeedback={(input) => {
                  setAnnouncement('');
                  feedback.mutate(input);
                }}
              />
            ))}
          </ul>
          {pageCount > 1 ? (
            <PaginationControls
              canNextPage={!interactionDisabled && page < pageCount}
              canPreviousPage={!interactionDisabled && page > 1}
              onPageChange={(pageIndex) => setPage(pageIndex + 1)}
              pageCount={pageCount}
              pageIndex={page - 1}
            />
          ) : null}
        </div>
      ) : null}
    </PageShell>
  );
}

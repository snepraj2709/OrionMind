'use client';

import { BookOpenText, Waypoints } from 'lucide-react';
import { type ReactNode, useEffect, useState } from 'react';

import { FilterField, PaginationControls } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  DataViewStatus,
  EmptyState,
  InlineError,
  NoResultsState,
} from '@/components/feedback';
import { PageHeader, PageShell } from '@/components/layout';
import { AppLink, SegmentedControl } from '@/components/navigation';
import { dataViewMessages } from '@/config/messages';
import { routes } from '@/config/routes';
import { useAuth } from '@/features/auth';
import { useOnlineStatus } from '@/hooks';

import { reviewPageSizeDefault } from './api-schema';
import type {
  ReviewCategoryFilter,
  ReviewListQuery,
  ReviewScope,
  ReviewStatus,
} from './model';
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

const categoryOptions = {
  entry_insight: [
    { label: 'All Entry Insights', value: 'all' },
    { label: 'Energy', value: 'energy' },
    { label: 'Self-knowledge', value: 'self_knowledge' },
    { label: 'Needs & beliefs', value: 'needs_beliefs' },
  ],
  pattern: [
    { label: 'All Patterns', value: 'all' },
    { label: 'Hidden drivers', value: 'hidden_driver' },
    { label: 'Recurring loops', value: 'recurring_loop' },
    { label: 'Inner tensions', value: 'inner_tension' },
  ],
} as const;

const statusOptions = [
  { label: 'Needs review', value: 'pending' },
  { label: 'Confirmed', value: 'confirmed' },
  { label: 'Partially confirmed', value: 'partially_confirmed' },
  { label: 'Rejected', value: 'rejected' },
] as const;

export interface ReviewScreenProps {
  repository?: ReviewRepository;
}

export function ReviewScreen({
  repository = reviewRepository,
}: ReviewScreenProps) {
  const { user } = useAuth();
  const isOnline = useOnlineStatus();
  const [scope, setScope] = useState<ReviewScope>('entry_insight');
  const [category, setCategory] = useState<ReviewCategoryFilter>('all');
  const [status, setStatus] = useState<ReviewStatus>('pending');
  const [page, setPage] = useState(1);
  const [announcement, setAnnouncement] = useState('');
  const queryInput: ReviewListQuery = {
    scope,
    category,
    status,
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
  const hasFilters = category !== 'all' || status !== 'pending';
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

  function clearFilters() {
    setCategory('all');
    setStatus('pending');
    setPage(1);
  }

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
          setCategory('all');
          setPage(1);
        }}
        value={scope}
      />

      <div className="flex flex-wrap items-end gap-4">
        <FilterField
          disabled={interactionDisabled}
          id="review-category"
          label="Category"
          onValueChange={(value) => {
            setCategory(value as ReviewCategoryFilter);
            setPage(1);
          }}
          options={[...categoryOptions[scope]]}
          value={category}
        />
        <FilterField
          disabled={interactionDisabled}
          id="review-status"
          label="Status"
          onValueChange={(value) => {
            setStatus(value as ReviewStatus);
            setPage(1);
          }}
          options={[...statusOptions]}
          value={status}
        />
      </div>

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

      {query.data?.pagination.total === 0 && !hasFilters ? (
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

      {query.data?.pagination.total === 0 && hasFilters ? (
        <NoResultsState
          action={
            <AppButton onClick={clearFilters} variant="secondary">
              Clear filters
            </AppButton>
          }
        />
      ) : null}

      {query.data && query.data.items.length > 0 ? (
        <div className="space-y-6">
          <ul aria-live="polite">
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

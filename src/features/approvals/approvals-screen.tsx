'use client';

import { Brain, Lightbulb, UserRound } from 'lucide-react';
import { type ReactNode, useState } from 'react';

import { FilterField, PaginationControls } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  DataViewStatus,
  EmptyState,
  InlineError,
  NoResultsState,
} from '@/components/feedback';
import { SearchControl } from '@/components/forms';
import { PageHeader, PageShell } from '@/components/layout';
import { AppLink, SegmentedControl } from '@/components/navigation';
import { themeRegistry } from '@/config/design-system';
import { dataViewMessages } from '@/config/messages';
import { routes } from '@/config/routes';
import { extractedItemKindPresentation } from '@/config/status';
import { useCollectionControls, useOnlineStatus } from '@/hooks';

import { approvalsRepository } from './mock-repository';
import type {
  ApprovalKindFilter,
  ApprovalRecord,
  ApprovalStatusFilter,
  ApprovalThemeFilter,
} from './model';
import { useApprovalDecisionMutation, useApprovalsQuery } from './queries';
import type { ApprovalsRepository } from './repository';
import { ReviewQueueItem } from './review-queue-item';

const reviewPageSize = 5;

const kindItems = [
  {
    icon: <Lightbulb aria-hidden="true" className="size-5" />,
    label: 'Ideas',
    value: 'idea',
  },
  {
    icon: <Brain aria-hidden="true" className="size-5" />,
    label: 'Memories',
    value: 'memory',
  },
  {
    icon: <UserRound aria-hidden="true" className="size-5" />,
    label: 'Reflections',
    value: 'reflection',
  },
] satisfies Array<{
  icon: ReactNode;
  label: string;
  value: Exclude<ApprovalKindFilter, 'all'>;
}>;

const themeOptions = [
  { label: 'All Themes', value: 'all' },
  ...Object.entries(themeRegistry).map(([value, presentation]) => ({
    label: presentation.label,
    value,
  })),
];

export interface ApprovalsScreenProps {
  repository?: ApprovalsRepository;
}

export function ApprovalsScreen({
  repository = approvalsRepository,
}: ApprovalsScreenProps) {
  const isOnline = useOnlineStatus();
  const [kind, setKind] = useState<ApprovalKindFilter>('idea');
  const [status, setStatus] = useState<ApprovalStatusFilter>('all');
  const [theme, setTheme] = useState<ApprovalThemeFilter>('all');
  const { clearSearch, pageIndex, pageSize, search, setPageIndex, setSearch } =
    useCollectionControls(reviewPageSize);
  const [lastDecision, setLastDecision] = useState<string>();

  const { query: approvalsQuery, viewStatus } = useApprovalsQuery(
    { kind, pageIndex, pageSize, search, status, theme },
    repository,
  );
  const decision = useApprovalDecisionMutation(repository, (item) => {
    setLastDecision(
      `${extractedItemKindPresentation[item.kind].label} ${item.status === 'approved' ? 'approved' : 'rejected'}.`,
    );
    setPageIndex(0);
  });

  const pageCount = approvalsQuery.data
    ? Math.ceil(approvalsQuery.data.total / pageSize)
    : 0;
  const hasFilters =
    kind !== 'idea' ||
    status !== 'all' ||
    theme !== 'all' ||
    search.trim().length > 0;

  function clearFilters() {
    setKind('idea');
    setStatus('all');
    setTheme('all');
    clearSearch();
  }

  function decisionState(item: ApprovalRecord) {
    const isCurrentItem = decision.variables?.id === item.id;
    if (!isCurrentItem || !decision.isPending) return undefined;
    return decision.variables?.status === 'approved' ? 'approve' : 'reject';
  }

  return (
    <PageShell className="space-y-8">
      <PageHeader
        description="Approve or dismiss what Orion extracted from your entries."
        title={routes.approvals.label}
      />

      <SegmentedControl
        ariaLabel="Review item type"
        items={kindItems}
        onValueChange={(value) => {
          setKind(value as Exclude<ApprovalKindFilter, 'all'>);
          setPageIndex(0);
        }}
        value={kind}
      />

      <SearchControl
        filters={
          <>
            <FilterField
              id="review-status"
              hideLabel
              label="Status"
              onValueChange={(value) => {
                setStatus(value as ApprovalStatusFilter);
                setPageIndex(0);
              }}
              options={[
                { label: 'All Status', value: 'all' },
                { label: 'Needs review', value: 'pending_approval' },
              ]}
              value={status}
            />
            <FilterField
              id="review-theme"
              hideLabel
              label="Theme"
              onValueChange={(value) => {
                setTheme(value as ApprovalThemeFilter);
                setPageIndex(0);
              }}
              options={themeOptions}
              value={theme}
            />
          </>
        }
        label="Search review queue"
        onSearch={setSearch}
        placeholder="Search extracted items…"
        value={search}
      />

      {!isOnline ? (
        <InlineError>
          You are offline. The review queue remains visible, but decisions are
          disabled until the connection returns.
        </InlineError>
      ) : null}

      {decision.isError ? (
        <InlineError>
          This item could not be decided. It may already have been reviewed;
          refresh the queue and try again.
        </InlineError>
      ) : null}

      <Typography aria-live="polite" className="sr-only" variant="bodySmall">
        {lastDecision}
      </Typography>

      <DataViewStatus
        initialError={dataViewMessages.approvals.initial}
        onRetry={() => void approvalsQuery.refetch()}
        refreshError={dataViewMessages.approvals.refresh}
        refreshingLabel="Refreshing review queue…"
        status={viewStatus}
      />

      {approvalsQuery.data?.totalAll === 0 ? (
        <EmptyState
          action={
            <AppButton asChild variant="secondary">
              <AppLink href={routes.entries.path}>Return to entries</AppLink>
            </AppButton>
          }
          description="New ideas, memories, and reflections will appear here after Orion reflects on an entry."
          title="You are all caught up"
        />
      ) : null}

      {approvalsQuery.data &&
      approvalsQuery.data.totalAll > 0 &&
      approvalsQuery.data.total === 0 ? (
        <NoResultsState
          action={
            <AppButton onClick={clearFilters} variant="secondary">
              Clear filters
            </AppButton>
          }
        />
      ) : null}

      {approvalsQuery.data && approvalsQuery.data.items.length > 0 ? (
        <div className="space-y-6">
          <ul aria-live="polite">
            {approvalsQuery.data.items.map((item) => (
              <ReviewQueueItem
                content={item.content}
                disabled={!isOnline || decision.isPending}
                key={item.id}
                loadingAction={decisionState(item)}
                onApprove={() =>
                  decision.mutate({ id: item.id, status: 'approved' })
                }
                onReject={() =>
                  decision.mutate({ id: item.id, status: 'rejected' })
                }
              />
            ))}
          </ul>
          <PaginationControls
            canNextPage={pageIndex + 1 < pageCount}
            canPreviousPage={pageIndex > 0}
            onPageChange={setPageIndex}
            pageCount={pageCount}
            pageIndex={pageIndex}
          />
        </div>
      ) : null}

      {hasFilters ? (
        <Typography className="sr-only" variant="bodySmall">
          Review filters are active.
        </Typography>
      ) : null}
    </PageShell>
  );
}

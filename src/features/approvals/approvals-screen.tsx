'use client';

import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useState } from 'react';

import {
  FilterBar,
  FilterField,
  PaginationControls,
  StatusBadge,
} from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  EmptyState,
  InlineError,
  NoResultsState,
  PageErrorState,
  SkeletonList,
} from '@/components/feedback';
import { SearchInput } from '@/components/forms';
import { PageHeader, PageShell } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { ApprovalActions, ReviewItemCard } from '@/components/shared';
import { entryDetailPath, routes } from '@/config/routes';
import { useOnlineStatus } from '@/hooks';
import { formatLongDate } from '@/lib/date';

import { approvalsRepository } from './mock-repository';
import type { ApprovalKindFilter, ApprovalRecord } from './model';
import type { ApprovalsRepository } from './repository';

export interface ApprovalsScreenProps {
  repository?: ApprovalsRepository;
}

export function ApprovalsScreen({
  repository = approvalsRepository,
}: ApprovalsScreenProps) {
  const isOnline = useOnlineStatus();
  const [kind, setKind] = useState<ApprovalKindFilter>('all');
  const [search, setSearch] = useState('');
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(5);
  const [lastDecision, setLastDecision] = useState<string>();

  const approvalsQuery = useQuery({
    queryKey: ['approvals', { kind, pageIndex, pageSize, search }],
    queryFn: () =>
      repository.listPendingApprovals({ kind, pageIndex, pageSize, search }),
    placeholderData: keepPreviousData,
  });
  const decision = useMutation({
    mutationFn: (input: Parameters<ApprovalsRepository['decideApproval']>[0]) =>
      repository.decideApproval(input),
    onSuccess: async (item) => {
      setLastDecision(
        `${item.kind === 'idea' ? 'Idea' : 'Memory'} ${item.status === 'approved' ? 'approved' : 'rejected'}.`,
      );
      await approvalsQuery.refetch();
    },
  });

  const pageCount = approvalsQuery.data
    ? Math.ceil(approvalsQuery.data.total / pageSize)
    : 0;
  const hasFilters = kind !== 'all' || search.trim().length > 0;

  function clearFilters() {
    setKind('all');
    setSearch('');
    setPageIndex(0);
  }

  function actionsFor(item: ApprovalRecord) {
    const isCurrentItem = decision.variables?.id === item.id;
    const loadingAction = isCurrentItem
      ? decision.variables?.status === 'approved'
        ? 'approve'
        : 'reject'
      : undefined;

    return (
      <ApprovalActions
        disabled={!isOnline || decision.isPending}
        loadingAction={decision.isPending ? loadingAction : undefined}
        onApprove={() => decision.mutate({ id: item.id, status: 'approved' })}
        onReject={() => decision.mutate({ id: item.id, status: 'rejected' })}
      />
    );
  }

  return (
    <PageShell className="space-y-8">
      <PageHeader
        description="Choose which ideas and memories should become part of your Orion record."
        title={routes.approvals.label}
      />

      <FilterBar
        actions={
          <AppButton
            leftIcon={<RefreshCw aria-hidden="true" className="size-4" />}
            loading={approvalsQuery.isFetching && !approvalsQuery.isPending}
            loadingLabel="Refreshing review queue"
            onClick={() => void approvalsQuery.refetch()}
            size="compact"
            variant="ghost"
          >
            Refresh
          </AppButton>
        }
        ariaLabel="Review filters"
      >
        <SearchInput
          label="Search review queue"
          onChange={(event) => {
            setSearch(event.target.value);
            setPageIndex(0);
          }}
          placeholder="Search ideas and memories"
          value={search}
        />
        <FilterField
          id="review-kind"
          label="Show"
          onValueChange={(value) => {
            setKind(value as ApprovalKindFilter);
            setPageIndex(0);
          }}
          options={[
            { label: 'Ideas and memories', value: 'all' },
            { label: 'Ideas', value: 'idea' },
            { label: 'Memories', value: 'memory' },
          ]}
          value={kind}
        />
      </FilterBar>

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

      {approvalsQuery.isPending ? <SkeletonList count={3} /> : null}

      {approvalsQuery.isError && !approvalsQuery.data ? (
        <PageErrorState
          action={
            <AppButton
              onClick={() => void approvalsQuery.refetch()}
              variant="secondary"
            >
              Retry
            </AppButton>
          }
          description="The review queue could not be loaded. Try again when you are ready."
          title="Review is unavailable"
        />
      ) : null}

      {approvalsQuery.isError && approvalsQuery.data ? (
        <InlineError>
          The queue could not be refreshed. The last loaded items remain
          visible.
        </InlineError>
      ) : null}

      {approvalsQuery.data?.totalAll === 0 ? (
        <EmptyState
          action={
            <AppButton asChild variant="secondary">
              <AppLink href={routes.entries.path}>Return to entries</AppLink>
            </AppButton>
          }
          description="New ideas and memories will appear here after Orion reflects on an entry."
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
          <div className="space-y-4">
            {approvalsQuery.data.items.map((item) => (
              <ReviewItemCard
                actions={actionsFor(item)}
                content={item.content}
                key={item.id}
                metadata={
                  <AppLink
                    className="type-body-small"
                    href={entryDetailPath(item.entryId)}
                  >
                    From {formatLongDate(item.entryDate)}
                  </AppLink>
                }
                status={<StatusBadge label="Needs review" variant="warning" />}
                title={item.kind === 'idea' ? 'Idea' : 'Memory'}
              />
            ))}
          </div>
          <PaginationControls
            canNextPage={pageIndex + 1 < pageCount}
            canPreviousPage={pageIndex > 0}
            onPageChange={setPageIndex}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(nextPageSize);
              setPageIndex(0);
            }}
            pageCount={pageCount}
            pageIndex={pageIndex}
            pageSize={pageSize}
            pageSizeOptions={[5, 10, 20]}
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

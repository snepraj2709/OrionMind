'use client';

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useState } from 'react';

import {
  FilterBar,
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
import { entryDetailPath, routes } from '@/config/routes';
import { useOnlineStatus } from '@/hooks';
import { formatLongDate } from '@/lib/date';
import {
  savedItemsRepository,
  type SavedItemKind,
  type SavedItemsRepository,
} from '@/services/saved-items';

import { ReviewItemCard } from './review-item-card';

export interface SavedItemsScreenProps {
  kind: SavedItemKind;
  title: string;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
  repository?: SavedItemsRepository;
}

export function SavedItemsScreen({
  description,
  emptyDescription,
  emptyTitle,
  kind,
  repository = savedItemsRepository,
  title,
}: SavedItemsScreenProps) {
  const isOnline = useOnlineStatus();
  const [search, setSearch] = useState('');
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(5);
  const query = useQuery({
    queryKey: ['saved-items', { kind, pageIndex, pageSize, search }],
    queryFn: () =>
      repository.listSavedItems({ kind, pageIndex, pageSize, search }),
    placeholderData: keepPreviousData,
  });
  const pageCount = query.data ? Math.ceil(query.data.total / pageSize) : 0;

  return (
    <PageShell className="space-y-8">
      <PageHeader description={description} title={title} />
      <FilterBar
        actions={
          <AppButton
            disabled={!isOnline}
            leftIcon={<RefreshCw aria-hidden="true" className="size-4" />}
            loading={query.isFetching && !query.isPending}
            loadingLabel={`Refreshing ${title.toLocaleLowerCase()}`}
            onClick={() => void query.refetch()}
            size="compact"
            variant="ghost"
          >
            Refresh
          </AppButton>
        }
        ariaLabel={`${title} filters`}
      >
        <SearchInput
          label={`Search ${title.toLocaleLowerCase()}`}
          onChange={(event) => {
            setSearch(event.target.value);
            setPageIndex(0);
          }}
          placeholder={`Search saved ${title.toLocaleLowerCase()}`}
          value={search}
        />
      </FilterBar>

      {!isOnline ? (
        <InlineError>
          You are offline. Previously loaded items remain available; refresh
          will resume when the connection returns.
        </InlineError>
      ) : null}

      {query.isPending ? <SkeletonList count={3} /> : null}
      {query.isError && !query.data ? (
        <PageErrorState
          action={
            <AppButton onClick={() => void query.refetch()} variant="secondary">
              Retry
            </AppButton>
          }
          description={`${title} could not be loaded. Try again when you are ready.`}
          title={`${title} are unavailable`}
        />
      ) : null}

      {query.isError && query.data ? (
        <InlineError>
          {title} could not be refreshed. The last loaded items remain visible.
        </InlineError>
      ) : null}

      {query.data?.totalAll === 0 ? (
        <EmptyState
          action={
            <AppButton asChild variant="secondary">
              <AppLink href={routes.entries.path}>Return to entries</AppLink>
            </AppButton>
          }
          description={emptyDescription}
          title={emptyTitle}
        />
      ) : null}

      {query.data && query.data.totalAll > 0 && query.data.total === 0 ? (
        <NoResultsState
          action={
            <AppButton
              onClick={() => {
                setSearch('');
                setPageIndex(0);
              }}
              variant="secondary"
            >
              Clear search
            </AppButton>
          }
        />
      ) : null}

      {query.data && query.data.items.length > 0 ? (
        <div className="space-y-6">
          {query.isFetching && !query.isPending ? (
            <Typography className="text-muted-foreground" variant="bodySmall">
              Refreshing {title.toLocaleLowerCase()}…
            </Typography>
          ) : null}
          <div className="space-y-4">
            {query.data.items.map((item) => (
              <ReviewItemCard
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
                status={<StatusBadge label="Saved" variant="success" />}
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
    </PageShell>
  );
}

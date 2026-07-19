'use client';

import {
  FilterBar,
  PaginationControls,
  StatusBadge,
} from '@/components/data-display';
import { AppButton } from '@/components/design-system';
import {
  DataViewStatus,
  EmptyState,
  InlineError,
  NoResultsState,
} from '@/components/feedback';
import { SearchInput } from '@/components/forms';
import { PageHeader, PageShell } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { entryDetailPath, routes } from '@/config/routes';
import { savedItemsDataViewMessages } from '@/config/messages';
import {
  extractedItemKindPresentation,
  savedItemStatusPresentation,
} from '@/config/status';
import { collectionPageSizeOptions } from '@/constants/pagination';
import {
  useCollectionControls,
  useOnlineStatus,
  useSavedItemsQuery,
} from '@/hooks';
import { formatLongDate } from '@/lib/date';
import {
  type SavedItemKind,
  type SavedItemsRepository,
} from '@/services/saved-items';

import { ReviewItemCard } from './review-item-card';
import { RefreshButton } from './refresh-button';

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
  repository,
  title,
}: SavedItemsScreenProps) {
  const isOnline = useOnlineStatus();
  const {
    clearSearch,
    pageIndex,
    pageSize,
    search,
    setPageIndex,
    setPageSize,
    setSearch,
  } = useCollectionControls();
  const { query, viewStatus } = useSavedItemsQuery(
    { kind, pageIndex, pageSize, search },
    repository,
  );
  const pageCount = query.data ? Math.ceil(query.data.total / pageSize) : 0;
  const errorMessages = savedItemsDataViewMessages(title);

  return (
    <PageShell className="space-y-8">
      <PageHeader description={description} title={title} />
      <FilterBar
        actions={
          <RefreshButton
            disabled={!isOnline}
            loading={query.isFetching && !query.isPending}
            loadingLabel={`Refreshing ${title.toLocaleLowerCase()}`}
            onClick={() => void query.refetch()}
          >
            Refresh
          </RefreshButton>
        }
        ariaLabel={`${title} filters`}
      >
        <SearchInput
          label={`Search ${title.toLocaleLowerCase()}`}
          onChange={(event) => {
            setSearch(event.target.value);
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

      <DataViewStatus
        initialError={errorMessages.initial}
        onRetry={() => void query.refetch()}
        refreshError={errorMessages.refresh}
        refreshingLabel={`Refreshing ${title.toLocaleLowerCase()}…`}
        retryDisabled={!isOnline}
        status={viewStatus}
      />

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
            <AppButton onClick={clearSearch} variant="secondary">
              Clear search
            </AppButton>
          }
        />
      ) : null}

      {query.data && query.data.items.length > 0 ? (
        <div className="space-y-6">
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
                status={
                  <StatusBadge
                    label={savedItemStatusPresentation.label}
                    variant={savedItemStatusPresentation.tone}
                  />
                }
                title={extractedItemKindPresentation[item.kind].label}
              />
            ))}
          </div>
          <PaginationControls
            canNextPage={pageIndex + 1 < pageCount}
            canPreviousPage={pageIndex > 0}
            onPageChange={setPageIndex}
            onPageSizeChange={setPageSize}
            pageCount={pageCount}
            pageIndex={pageIndex}
            pageSize={pageSize}
            pageSizeOptions={collectionPageSizeOptions}
          />
        </div>
      ) : null}
    </PageShell>
  );
}

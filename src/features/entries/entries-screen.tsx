'use client';

import { PenLine } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import { EntryCard } from '@/components/cards';
import {
  FilterBar,
  FilterField,
  PaginationControls,
  StatusBadge,
  ThemeBadge,
} from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  DataViewStatus,
  EmptyState,
  NoResultsState,
} from '@/components/feedback';
import { SearchInput } from '@/components/forms';
import { PageHeader, PageShell } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { RefreshButton } from '@/components/shared';
import { entryDetailPath, routes } from '@/config/routes';
import { dataViewMessages } from '@/config/messages';
import { entryStatusPresentation } from '@/config/status';
import { collectionPageSizeOptions } from '@/constants/pagination';
import { useCollectionControls } from '@/hooks';
import { formatLongDate } from '@/lib/date';

import { entriesRepository } from './mock-repository';
import type { EntryStatusFilter } from './model';
import { useEntriesQuery } from './queries';
import type { EntriesRepository } from './repository';

export interface EntriesScreenProps {
  repository?: EntriesRepository;
}

export function EntriesScreen({
  repository = entriesRepository,
}: EntriesScreenProps) {
  const [status, setStatus] = useState<EntryStatusFilter>('all');
  const {
    clearSearch,
    pageIndex,
    pageSize,
    search,
    setPageIndex,
    setPageSize,
    setSearch,
  } = useCollectionControls();

  const { query, viewStatus } = useEntriesQuery(
    { pageIndex, pageSize, search, status },
    repository,
  );

  const pageCount = query.data ? Math.ceil(query.data.total / pageSize) : 0;
  const hasFilters = search.trim().length > 0 || status !== 'all';

  function clearFilters() {
    clearSearch();
    setStatus('all');
  }

  return (
    <PageShell className="space-y-8">
      <PageHeader
        actions={
          <AppButton asChild leftIcon={<PenLine aria-hidden="true" />}>
            <Link href={routes.newEntry.path}>Add Entry</Link>
          </AppButton>
        }
        description="A private record of what you noticed, felt, and understood."
        title={routes.entries.label}
      />

      <FilterBar
        actions={
          <RefreshButton
            loading={query.isFetching && !query.isPending}
            loadingLabel="Refreshing entries"
            onClick={() => void query.refetch()}
          >
            Refresh
          </RefreshButton>
        }
        ariaLabel="Entry filters"
      >
        <SearchInput
          label="Search entries"
          onChange={(event) => {
            setSearch(event.target.value);
          }}
          placeholder="Search your writing"
          value={search}
        />
        <FilterField
          id="entry-status"
          label="Status"
          onValueChange={(value) => {
            setStatus(value as EntryStatusFilter);
            setPageIndex(0);
          }}
          options={[
            { label: 'All entries', value: 'all' },
            {
              label: entryStatusPresentation.completed.filterLabel,
              value: 'completed',
            },
            {
              label: entryStatusPresentation.processing.filterLabel,
              value: 'processing',
            },
            {
              label: entryStatusPresentation.failed.filterLabel,
              value: 'failed',
            },
          ]}
          value={status}
        />
      </FilterBar>

      <DataViewStatus
        initialError={dataViewMessages.entries.initial}
        onRetry={() => void query.refetch()}
        refreshError={dataViewMessages.entries.refresh}
        refreshingLabel="Refreshing entries…"
        skeletonCount={4}
        status={viewStatus}
      />

      {query.data?.totalAll === 0 ? (
        <EmptyState
          action={
            <AppButton asChild>
              <Link href={routes.newEntry.path}>Add your first entry</Link>
            </AppButton>
          }
          description="Start with a thought, a moment, or a question you want to return to."
          title="Your journal is ready"
        />
      ) : null}

      {query.data && query.data.totalAll > 0 && query.data.total === 0 ? (
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
          <div aria-live="polite" className="space-y-4">
            {query.data.items.map((entry) => {
              const statusConfig = entryStatusPresentation[entry.status];

              return (
                <AppLink
                  className="block w-full"
                  href={entryDetailPath(entry.id)}
                  key={entry.id}
                >
                  <EntryCard
                    excerpt={entry.content}
                    footer={
                      entry.themes.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {entry.themes.map((theme) => (
                            <ThemeBadge key={theme} theme={theme} />
                          ))}
                        </div>
                      ) : (
                        <Typography
                          className="text-muted-foreground"
                          variant="bodySmall"
                        >
                          Themes will appear after processing.
                        </Typography>
                      )
                    }
                    metadata={`${entry.inputType === 'voice' ? 'Voice' : 'Text'} entry`}
                    status={
                      <StatusBadge
                        label={statusConfig.label}
                        variant={statusConfig.tone}
                      />
                    }
                    title={formatLongDate(entry.date)}
                  />
                </AppLink>
              );
            })}
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

      {hasFilters ? (
        <Typography className="sr-only" variant="bodySmall">
          Entry filters are active.
        </Typography>
      ) : null}
    </PageShell>
  );
}

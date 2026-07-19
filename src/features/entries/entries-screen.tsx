'use client';

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { PenLine, RefreshCw } from 'lucide-react';
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
  EmptyState,
  NoResultsState,
  PageErrorState,
  SkeletonList,
} from '@/components/feedback';
import { SearchInput } from '@/components/forms';
import { PageHeader, PageShell } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { entryDetailPath, routes } from '@/config/routes';
import { formatLongDate } from '@/lib/date';

import { entriesRepository } from './mock-repository';
import type { EntryStatus, EntryStatusFilter } from './model';
import { entryKeys } from './query-keys';
import type { EntriesRepository } from './repository';

const statusPresentation: Record<
  EntryStatus,
  { label: string; variant: 'success' | 'processing' | 'error' }
> = {
  completed: { label: 'Complete', variant: 'success' },
  processing: { label: 'Processing', variant: 'processing' },
  failed: { label: 'Processing failed', variant: 'error' },
};

export interface EntriesScreenProps {
  repository?: EntriesRepository;
}

export function EntriesScreen({
  repository = entriesRepository,
}: EntriesScreenProps) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<EntryStatusFilter>('all');
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(5);

  const query = useQuery({
    queryKey: entryKeys.list({ pageIndex, pageSize, search, status }),
    queryFn: () =>
      repository.listEntries({ pageIndex, pageSize, search, status }),
    placeholderData: keepPreviousData,
  });

  const pageCount = query.data ? Math.ceil(query.data.total / pageSize) : 0;
  const hasFilters = search.trim().length > 0 || status !== 'all';

  function clearFilters() {
    setSearch('');
    setStatus('all');
    setPageIndex(0);
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
          <AppButton
            leftIcon={<RefreshCw aria-hidden="true" className="size-4" />}
            loading={query.isFetching && !query.isPending}
            loadingLabel="Refreshing entries"
            onClick={() => void query.refetch()}
            size="compact"
            variant="ghost"
          >
            Refresh
          </AppButton>
        }
        ariaLabel="Entry filters"
      >
        <SearchInput
          label="Search entries"
          onChange={(event) => {
            setSearch(event.target.value);
            setPageIndex(0);
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
            { label: 'Complete', value: 'completed' },
            { label: 'Processing', value: 'processing' },
            { label: 'Failed', value: 'failed' },
          ]}
          value={status}
        />
      </FilterBar>

      {query.isPending ? <SkeletonList count={4} /> : null}

      {query.isError ? (
        <PageErrorState
          action={
            <AppButton onClick={() => void query.refetch()} variant="secondary">
              Retry
            </AppButton>
          }
          description="Your entries could not be loaded. Try again when you are ready."
          title="Entries are unavailable"
        />
      ) : null}

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
            {query.isFetching && !query.isPending ? (
              <Typography className="text-muted-foreground" variant="bodySmall">
                Refreshing entries…
              </Typography>
            ) : null}
            {query.data.items.map((entry) => {
              const statusConfig = statusPresentation[entry.status];

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
                        variant={statusConfig.variant}
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
          Entry filters are active.
        </Typography>
      ) : null}
    </PageShell>
  );
}

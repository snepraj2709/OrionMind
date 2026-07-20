'use client';

import { PenLine } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import { FilterField, PaginationControls } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  DataViewStatus,
  EmptyState,
  NoResultsState,
} from '@/components/feedback';
import { SearchControl } from '@/components/forms';
import { PageHeader, PageShell } from '@/components/layout';
import { routes } from '@/config/routes';
import { dataViewMessages } from '@/config/messages';
import { entryStatusPresentation } from '@/config/status';
import { useCollectionControls } from '@/hooks';

import { EntryListItem } from './entry-list-item';
import { entriesRepository } from './mock-repository';
import type { EntryStatusFilter } from './model';
import { useEntriesQuery } from './queries';
import type { EntriesRepository } from './repository';

export interface EntriesScreenProps {
  repository?: EntriesRepository;
  pendingReviewCount?: number;
}

export function EntriesScreen({
  pendingReviewCount = 0,
  repository = entriesRepository,
}: EntriesScreenProps) {
  const [status, setStatus] = useState<EntryStatusFilter>('all');
  const { clearSearch, pageIndex, pageSize, search, setPageIndex, setSearch } =
    useCollectionControls();
  const { query, viewStatus } = useEntriesQuery(
    { pageIndex, pageSize, search, status },
    repository,
  );

  const pageCount = query.data ? Math.ceil(query.data.total / pageSize) : 0;
  const hasFilters = search.trim().length > 0 || status !== 'all';
  const entryCount = query.data?.totalAll;

  function clearFilters() {
    clearSearch();
    setStatus('all');
  }

  return (
    <PageShell className="space-y-6">
      <PageHeader
        actions={
          <AppButton asChild leftIcon={<PenLine aria-hidden="true" />}>
            <Link href={routes.newEntry.path}>New entry</Link>
          </AppButton>
        }
        description={
          <span
            aria-label={`${entryCount ?? 'Loading'} ${entryCount === 1 ? 'entry' : 'entries'}, ${pendingReviewCount} awaiting review`}
            aria-live="polite"
          >
            {entryCount === undefined
              ? 'Loading entries'
              : `${entryCount} ${entryCount === 1 ? 'entry' : 'entries'}`}{' '}
            ·{' '}
            <span className="text-status-warning">
              {pendingReviewCount} awaiting review
            </span>
          </span>
        }
        title={routes.entries.label}
      />

      <SearchControl
        className="pb-3"
        filters={
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
        }
        inputClassName="bg-background"
        label="Search entries"
        onSearch={setSearch}
        placeholder="Search your writing"
        value={search}
      />

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
        <div>
          <ul aria-live="polite">
            {query.data.items.map((entry) => (
              <EntryListItem entry={entry} key={entry.id} />
            ))}
          </ul>

          <div className="pt-4">
            <PaginationControls
              canNextPage={pageIndex + 1 < pageCount}
              canPreviousPage={pageIndex > 0}
              onPageChange={setPageIndex}
              pageCount={pageCount}
              pageIndex={pageIndex}
            />
          </div>
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

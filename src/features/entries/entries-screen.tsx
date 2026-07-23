'use client';

import { PenLine } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { PaginationControls } from '@/components/data-display';
import { AppButton } from '@/components/design-system';
import { DataViewStatus, EmptyState } from '@/components/feedback';
import { PageHeader, PageShell } from '@/components/layout';
import { routes } from '@/config/routes';
import { dataViewMessages } from '@/config/messages';

import { EntryListItem } from './entry-list-item';
import { useEntriesQuery } from './queries';
import {
  entriesListRepository,
  type EntriesListRepository,
} from './repository';

export interface EntriesScreenProps {
  repository?: EntriesListRepository;
  pendingReviewCount?: number | null;
}

export function EntriesScreen({
  pendingReviewCount,
  repository = entriesListRepository,
}: EntriesScreenProps) {
  const [pageIndex, setPageIndex] = useState(0);
  const pageSize = 10;
  const { query, viewStatus } = useEntriesQuery(
    { pageIndex, pageSize },
    repository,
  );

  const pageCount = query.data
    ? Math.ceil(query.data.total / query.data.pageSize)
    : 0;
  const responsePageIndex = query.data ? query.data.page - 1 : pageIndex;
  const displayedPageIndex = query.isPlaceholderData
    ? pageIndex
    : responsePageIndex;
  const entryCount = query.data?.total;
  const reviewCountLabel =
    pendingReviewCount === undefined
      ? 'Loading review count'
      : pendingReviewCount === null
        ? 'Review count unavailable'
        : `${pendingReviewCount} awaiting review`;
  const reviewCountClassName =
    typeof pendingReviewCount === 'number' && pendingReviewCount > 0
      ? 'text-status-warning'
      : 'text-muted-foreground';

  useEffect(() => {
    if (
      query.data &&
      !query.isPlaceholderData &&
      query.data.total > 0 &&
      query.data.items.length === 0 &&
      responsePageIndex >= pageCount
    ) {
      const timer = window.setTimeout(
        () => setPageIndex(Math.max(0, pageCount - 1)),
        0,
      );
      return () => window.clearTimeout(timer);
    }
  }, [
    pageCount,
    query.data,
    query.isPlaceholderData,
    responsePageIndex,
    setPageIndex,
  ]);

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
            aria-label={`${entryCount ?? 'Loading'} ${entryCount === 1 ? 'entry' : 'entries'}, ${reviewCountLabel}`}
            aria-live="polite"
          >
            {entryCount === undefined
              ? 'Loading entries'
              : `${entryCount} ${entryCount === 1 ? 'entry' : 'entries'}`}{' '}
            · <span className={reviewCountClassName}>{reviewCountLabel}</span>
          </span>
        }
        title={routes.entries.label}
      />

      <DataViewStatus
        initialError={dataViewMessages.entries.initial}
        onRetry={() => void query.refetch()}
        refreshError={dataViewMessages.entries.refresh}
        status={viewStatus}
      />

      {query.data?.total === 0 ? (
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

      {query.data && query.data.items.length > 0 ? (
        <div>
          <ul aria-live="polite">
            {query.data.items.map((entry) => (
              <EntryListItem entry={entry} key={entry.id} />
            ))}
          </ul>

          <div className="pt-4">
            <PaginationControls
              canNextPage={displayedPageIndex + 1 < pageCount}
              canPreviousPage={displayedPageIndex > 0}
              onPageChange={setPageIndex}
              pageCount={pageCount}
              pageIndex={displayedPageIndex}
            />
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}

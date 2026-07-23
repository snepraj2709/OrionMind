'use client';

import { ArrowLeft } from 'lucide-react';

import { Surface } from '@/components/cards';
import { StatusBadge, ThemeBadge } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  DataViewStatus,
  EmptyState,
  InlineError,
  PageErrorState,
  ProcessingState,
} from '@/components/feedback';
import { PageHeader, PageShell, Section } from '@/components/layout';
import { RefreshButton, ReviewItemCard } from '@/components/shared';
import { AppLink, Breadcrumbs } from '@/components/navigation';
import { routes } from '@/config/routes';
import { dataViewMessages } from '@/config/messages';
import {
  approvalStatusPresentation,
  entryStatusPresentation,
  extractedItemKindPresentation,
} from '@/config/status';
import { useOnlineStatus } from '@/hooks';
import { formatLongDate } from '@/lib/date';

import type { EntryDetail, ExtractedItem } from './model';
import { useEntryQuery, useRetryEntryMutation } from './queries';
import {
  entryDetailRepository,
  type EntryDetailRepository,
} from './repository';

function ExtractedItemView({ item }: { item: ExtractedItem }) {
  const presentation = approvalStatusPresentation[item.status];

  return (
    <ReviewItemCard
      content={item.content}
      status={
        <StatusBadge label={presentation.label} variant={presentation.tone} />
      }
      title={extractedItemKindPresentation[item.kind].label}
    />
  );
}

function CompletedEntry({ entry }: { entry: EntryDetail }) {
  const extractedItems = [...entry.ideas, ...entry.memories];

  return (
    <div className="space-y-10">
      <Surface className="gap-6 p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge
            label={entryStatusPresentation.completed.label}
            variant={entryStatusPresentation.completed.tone}
          />
          <Typography className="text-muted-foreground" variant="metadata">
            {entry.inputType === 'voice' ? 'Voice transcript' : 'Text entry'}
          </Typography>
        </div>
        <Typography className="text-measure-wide" variant="journalExcerpt">
          {entry.content}
        </Typography>
      </Surface>

      <Section
        description="The strongest themes Orion found in this entry."
        title="Themes"
      >
        {entry.themes.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {entry.themes.map((theme) => (
              <ThemeBadge key={theme} theme={theme} />
            ))}
          </div>
        ) : (
          <Typography className="text-muted-foreground" variant="body">
            No themes were identified in this entry.
          </Typography>
        )}
      </Section>

      <Section
        description="Ideas and memories Orion found in this entry. Reviewable insights appear separately on Review."
        title="Extracted items"
      >
        {extractedItems.length === 0 ? (
          <EmptyState
            className="py-8"
            description="This entry did not produce any extracted ideas or memories."
            title="No extracted items"
          />
        ) : (
          <div aria-live="polite" className="space-y-4">
            {extractedItems.map((item) => (
              <ExtractedItemView item={item} key={item.id} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

export interface EntryDetailScreenProps {
  entryId: string;
  repository?: EntryDetailRepository;
}

export function EntryDetailScreen({
  entryId,
  repository = entryDetailRepository,
}: EntryDetailScreenProps) {
  const isOnline = useOnlineStatus();
  const { query: entryQuery, viewStatus } = useEntryQuery(entryId, repository);
  const retry = useRetryEntryMutation(entryId, repository);

  const entry = entryQuery.data;
  const title = entry ? formatLongDate(entry.date) : routes.entryDetail.label;

  return (
    <PageShell className="space-y-8">
      <PageHeader
        actions={
          <>
            <AppLink className="gap-2" href={routes.entries.path}>
              <ArrowLeft aria-hidden="true" className="size-4" />
              Back to entries
            </AppLink>
            <RefreshButton
              loading={entryQuery.isFetching && !entryQuery.isPending}
              loadingLabel="Refreshing entry"
              onClick={() => void entryQuery.refetch()}
            >
              Refresh
            </RefreshButton>
          </>
        }
        breadcrumbs={
          <Breadcrumbs
            items={[
              { href: routes.entries.path, label: routes.entries.label },
              { label: title },
            ]}
          />
        }
        description="Your original words and the patterns Orion found within them."
        title={title}
      />

      <DataViewStatus
        initialError={dataViewMessages.entryDetail.initial}
        onRetry={() => void entryQuery.refetch()}
        refreshError={dataViewMessages.entryDetail.refresh}
        refreshingLabel="Refreshing entry…"
        status={viewStatus}
      />

      {entryQuery.isSuccess && !entry ? (
        <EmptyState
          action={
            <AppButton asChild variant="secondary">
              <AppLink href={routes.entries.path}>Return to entries</AppLink>
            </AppButton>
          }
          description="It may have been removed, or this link may no longer be valid."
          title="Entry not found"
        />
      ) : null}

      {entry?.status === 'processing' ? (
        <div className="space-y-6">
          <Surface className="p-6 sm:p-8">
            <Typography className="text-measure-wide" variant="journalExcerpt">
              {entry.content}
            </Typography>
          </Surface>
          <ProcessingState
            description="Your entry is safe. Themes, ideas, and memories will appear here when reflection is complete."
            title="Orion is reflecting on this entry"
          />
        </div>
      ) : null}

      {entry?.status === 'pending' ? (
        <div className="space-y-6">
          <Surface className="p-6 sm:p-8">
            <Typography className="text-measure-wide" variant="journalExcerpt">
              {entry.content}
            </Typography>
          </Surface>
          <ProcessingState
            description="Your entry is safe and waiting for Orion to begin reflection. Refresh when you are ready to check its progress."
            title="Entry is queued for reflection"
          />
        </div>
      ) : null}

      {entry?.status === 'failed' ? (
        <div className="space-y-6">
          <Surface className="p-6 sm:p-8">
            <Typography className="text-measure-wide" variant="journalExcerpt">
              {entry.content}
            </Typography>
          </Surface>
          <PageErrorState
            action={
              <AppButton
                disabled={!isOnline || retry.isPending}
                loading={retry.isPending}
                loadingLabel="Retrying reflection"
                onClick={() => retry.mutate()}
              >
                Retry reflection
              </AppButton>
            }
            description={
              !isOnline
                ? 'You are offline. Your original entry is safe; retry will return when you reconnect.'
                : (entry.processingError ??
                  'Orion could not complete this reflection. Your original entry is safe.')
            }
            title="Reflection did not finish"
          />
          {retry.isError ? (
            <InlineError>
              Reflection could not be restarted. Your original entry remains
              safe; try again later.
            </InlineError>
          ) : null}
        </div>
      ) : null}

      {entry?.status === 'completed' ? <CompletedEntry entry={entry} /> : null}
    </PageShell>
  );
}

'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, RefreshCw } from 'lucide-react';

import { Surface } from '@/components/cards';
import { StatusBadge, ThemeBadge } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  EmptyState,
  InlineError,
  PageErrorState,
  ProcessingState,
  SkeletonList,
} from '@/components/feedback';
import { PageHeader, PageShell, Section } from '@/components/layout';
import { ApprovalActions, ReviewItemCard } from '@/components/shared';
import { AppLink, Breadcrumbs } from '@/components/navigation';
import { routes } from '@/config/routes';
import { useOnlineStatus } from '@/hooks';
import { formatLongDate } from '@/lib/date';

import { entriesRepository } from './mock-repository';
import type {
  ApprovalStatus,
  EntryDetail,
  ExtractedItem,
  ExtractedItemKind,
} from './model';
import { entryKeys } from './query-keys';
import type { EntriesRepository } from './repository';

const approvalPresentation: Record<
  ApprovalStatus,
  { label: string; variant: 'warning' | 'success' | 'neutral' }
> = {
  pending_approval: { label: 'Needs review', variant: 'warning' },
  approved: { label: 'Approved', variant: 'success' },
  rejected: { label: 'Not saved', variant: 'neutral' },
};

interface DecisionInput {
  entryId: string;
  itemId: string;
  kind: ExtractedItemKind;
  status: Exclude<ApprovalStatus, 'pending_approval'>;
}

function ExtractedItemView({
  decision,
  disabled,
  entryId,
  item,
}: {
  decision: ReturnType<typeof useDecisionMutation>;
  disabled: boolean;
  entryId: string;
  item: ExtractedItem;
}) {
  const presentation = approvalPresentation[item.status];
  const isCurrentItem = decision.variables?.itemId === item.id;
  const loadingAction = isCurrentItem
    ? decision.variables?.status === 'approved'
      ? 'approve'
      : 'reject'
    : undefined;

  return (
    <ReviewItemCard
      actions={
        item.status === 'pending_approval' ? (
          <ApprovalActions
            disabled={disabled || decision.isPending}
            loadingAction={decision.isPending ? loadingAction : undefined}
            onApprove={() =>
              decision.mutate({
                entryId,
                itemId: item.id,
                kind: item.kind,
                status: 'approved',
              })
            }
            onReject={() =>
              decision.mutate({
                entryId,
                itemId: item.id,
                kind: item.kind,
                status: 'rejected',
              })
            }
          />
        ) : undefined
      }
      content={item.content}
      status={
        <StatusBadge
          label={presentation.label}
          variant={presentation.variant}
        />
      }
      title={item.kind === 'idea' ? 'Idea' : 'Memory'}
    />
  );
}

function useDecisionMutation(
  repository: EntriesRepository,
  queryClient: ReturnType<typeof useQueryClient>,
) {
  return useMutation({
    mutationFn: (input: DecisionInput) => repository.decideExtractedItem(input),
    onSuccess: (entry) => {
      queryClient.setQueryData(entryKeys.detail(entry.id), entry);
      void queryClient.invalidateQueries({ queryKey: entryKeys.lists });
    },
  });
}

function CompletedEntry({
  decision,
  entry,
  isOnline,
}: {
  decision: ReturnType<typeof useDecisionMutation>;
  entry: EntryDetail;
  isOnline: boolean;
}) {
  const extractedItems = [...entry.ideas, ...entry.memories];

  return (
    <div className="space-y-10">
      <Surface className="gap-6 p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge label="Complete" variant="success" />
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
        description="Choose which extracted ideas and memories belong in your Orion record."
        title="Ideas and memories"
      >
        {!isOnline ? (
          <InlineError>
            You are offline. Your entry remains available, but review actions
            will return when the connection is restored.
          </InlineError>
        ) : null}
        {decision.isError ? (
          <InlineError>
            This review decision could not be saved. It may already have been
            decided; refresh the entry and try again.
          </InlineError>
        ) : null}
        {extractedItems.length === 0 ? (
          <EmptyState
            className="py-8"
            description="This entry did not produce an idea or memory that needs your review."
            title="Nothing to review"
          />
        ) : (
          <div aria-live="polite" className="space-y-4">
            {extractedItems.map((item) => (
              <ExtractedItemView
                decision={decision}
                disabled={!isOnline}
                entryId={entry.id}
                item={item}
                key={item.id}
              />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

export interface EntryDetailScreenProps {
  entryId: string;
  repository?: EntriesRepository;
}

export function EntryDetailScreen({
  entryId,
  repository = entriesRepository,
}: EntryDetailScreenProps) {
  const isOnline = useOnlineStatus();
  const queryClient = useQueryClient();
  const entryQuery = useQuery({
    queryKey: entryKeys.detail(entryId),
    queryFn: () => repository.getEntry(entryId),
  });
  const decision = useDecisionMutation(repository, queryClient);
  const retry = useMutation({
    mutationFn: () => repository.retryEntry(entryId),
    onSuccess: (entry) => {
      queryClient.setQueryData(entryKeys.detail(entry.id), entry);
      void queryClient.invalidateQueries({ queryKey: entryKeys.lists });
    },
  });

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
            <AppButton
              leftIcon={<RefreshCw aria-hidden="true" />}
              loading={entryQuery.isFetching && !entryQuery.isPending}
              loadingLabel="Refreshing entry"
              onClick={() => void entryQuery.refetch()}
              size="compact"
              variant="ghost"
            >
              Refresh
            </AppButton>
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

      {entryQuery.isPending ? <SkeletonList count={3} /> : null}

      {entryQuery.isError && !entry ? (
        <PageErrorState
          action={
            <AppButton
              leftIcon={<RefreshCw aria-hidden="true" />}
              onClick={() => void entryQuery.refetch()}
              variant="secondary"
            >
              Retry
            </AppButton>
          }
          description="This entry could not be loaded. Try again when you are ready."
          title="Entry unavailable"
        />
      ) : null}

      {entryQuery.isError && entry ? (
        <InlineError>
          This entry could not be refreshed. The last loaded version remains
          visible.
        </InlineError>
      ) : null}

      {entryQuery.isFetching && entry ? (
        <Typography
          aria-live="polite"
          className="text-muted-foreground"
          role="status"
          variant="bodySmall"
        >
          Refreshing entry…
        </Typography>
      ) : null}

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
                disabled={!isOnline}
                leftIcon={<RefreshCw aria-hidden="true" />}
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

      {entry?.status === 'completed' ? (
        <CompletedEntry decision={decision} entry={entry} isOnline={isOnline} />
      ) : null}
    </PageShell>
  );
}

'use client';

import { useMemo, useState } from 'react';

import { AppButton, Typography } from '@/components/design-system';
import {
  DataViewStatus,
  EmptyState,
  InlineError,
  NoResultsState,
} from '@/components/feedback';
import { PageHeader, PageShell, Section } from '@/components/layout';
import { AppLink, SegmentedControl } from '@/components/navigation';
import { EvidenceDrawer, RefreshButton } from '@/components/shared';
import { dataViewMessages } from '@/config/messages';
import { routes } from '@/config/routes';
import { useOnlineStatus } from '@/hooks';
import type { EvidenceItem } from '@/types/evidence';

import { deriveReflectionViewModel } from './adapter';
import { HiddenDriverCard } from './hidden-driver-card';
import { InnerTensionCard } from './inner-tension-card';
import { reflectionsRepository } from './mock-repository';
import type {
  ReflectionRange,
  ReflectionResponse,
  ReflectionView,
} from './model';
import { useReflectionEntriesQuery } from './queries';
import { RecurringLoop } from './recurring-loop';
import { ReflectionTabs } from './reflection-tabs';
import type { ReflectionsRepository } from './repository';

const rangeDateFormatter = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
});

export interface ReflectionsScreenProps {
  repository?: ReflectionsRepository;
}

export function ReflectionsScreen({
  repository = reflectionsRepository,
}: ReflectionsScreenProps) {
  const [range, setRange] = useState<ReflectionRange>('all');
  const [activeView, setActiveView] =
    useState<ReflectionView>('hidden-drivers');
  const [responses, setResponses] = useState<
    Record<string, ReflectionResponse>
  >({});
  const [drawerItems, setDrawerItems] = useState<EvidenceItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isOnline = useOnlineStatus();

  const { query: entriesQuery, viewStatus } = useReflectionEntriesQuery(
    range,
    repository,
  );
  const viewModel = useMemo(
    () =>
      entriesQuery.data
        ? deriveReflectionViewModel(entriesQuery.data.entries)
        : undefined,
    [entriesQuery.data],
  );

  function openEvidence(items: EvidenceItem[]) {
    setDrawerItems(items);
    setDrawerOpen(true);
  }

  function handleRangeChange(nextRange: ReflectionRange) {
    setRange(nextRange);
    setResponses({});
    setDrawerOpen(false);
  }

  function setResponse(key: string, response: ReflectionResponse) {
    setResponses((current) => ({ ...current, [key]: response }));
  }

  const activeEvidence = useMemo(() => {
    if (!viewModel) return [];
    if (activeView === 'hidden-drivers') return viewModel.hiddenDriver.evidence;
    if (activeView === 'recurring-loops') return viewModel.loop.evidence;
    return viewModel.tensions.flatMap((tension) => tension.evidence);
  }, [activeView, viewModel]);

  const subtitle =
    viewModel && viewModel.entryCount > 0
      ? `Patterns taking shape across ${viewModel.entryCount} entries from ${rangeDateFormatter.format(new Date(viewModel.from))}–${rangeDateFormatter.format(new Date(viewModel.to))}.`
      : 'A connected view of patterns across your journal history.';

  const successPanels = viewModel
    ? {
        'hidden-drivers': (
          <HiddenDriverCard
            driver={viewModel.hiddenDriver}
            onResponseChange={(response) =>
              setResponse('hidden-drivers', response)
            }
            onViewEvidence={() => openEvidence(viewModel.hiddenDriver.evidence)}
            response={responses['hidden-drivers']}
          />
        ),
        'recurring-loops': (
          <Section
            description={viewModel.loop.description}
            headingId="recurring-loops-heading"
            title={viewModel.loop.title}
          >
            <RecurringLoop
              loop={viewModel.loop}
              onResponseChange={(response) =>
                setResponse('recurring-loops', response)
              }
              onViewEvidence={() => openEvidence(viewModel.loop.evidence)}
              response={responses['recurring-loops']}
            />
          </Section>
        ),
        'inner-tensions': (
          <Section
            headingId="inner-tensions-heading"
            title="Needs you may be trying to hold at the same time"
          >
            <div className="space-y-4">
              {viewModel.tensions.map((tension) => (
                <InnerTensionCard
                  key={tension.id}
                  onResponseChange={(response) =>
                    setResponse(tension.id, response)
                  }
                  onViewEvidence={() => openEvidence(tension.evidence)}
                  response={responses[tension.id]}
                  tension={tension}
                />
              ))}
            </div>
          </Section>
        ),
      }
    : undefined;

  return (
    <PageShell className="space-y-8">
      <PageHeader
        actions={
          <>
            <SegmentedControl
              ariaLabel="Reflection date range"
              items={[
                { label: 'Last 7 days', value: '7d' },
                { label: 'Last 30 days', value: '30d' },
                { label: 'All entries', value: 'all' },
              ]}
              onValueChange={(value) =>
                handleRangeChange(value as ReflectionRange)
              }
              value={range}
              variant="strong"
            />
            {viewModel && viewModel.entryCount >= 5 ? (
              <AppButton
                onClick={() => openEvidence(activeEvidence)}
                size="compact"
                variant="link"
              >
                Why am I seeing this?
              </AppButton>
            ) : null}
            <RefreshButton
              aria-label="Refresh reflections"
              disabled={!isOnline}
              loading={entriesQuery.isFetching}
              loadingLabel="Refreshing reflections"
              onClick={() => void entriesQuery.refetch()}
              variant="icon"
            />
          </>
        }
        description={subtitle}
        title={routes.reflections.label}
      />

      <DataViewStatus
        initialError={dataViewMessages.reflections.initial}
        onRetry={() => void entriesQuery.refetch()}
        refreshError={dataViewMessages.reflections.refresh}
        refreshingAriaLabel="Refreshing reflections"
        refreshingLabel="Refreshing reflections… Your current view will stay in place."
        retryDisabled={!isOnline}
        skeletonCount={1}
        status={viewStatus}
      />

      {!isOnline && entriesQuery.data ? (
        <InlineError>
          You are offline. Orion is showing the last available reflections;
          refresh will resume when your connection returns.
        </InlineError>
      ) : null}

      {viewModel?.entryCount === 0 &&
      entriesQuery.data?.totalAvailable === 0 ? (
        <EmptyState
          action={
            <AppButton asChild>
              <AppLink href={routes.newEntry.path}>
                Write your first entry
              </AppLink>
            </AppButton>
          }
          description="Longitudinal patterns begin with the moments you choose to record."
          title="Your reflection history is ready to begin"
        />
      ) : null}

      {viewModel?.entryCount === 0 &&
      (entriesQuery.data?.totalAvailable ?? 0) > 0 ? (
        <NoResultsState
          action={
            <AppButton
              onClick={() => handleRangeChange('all')}
              variant="secondary"
            >
              Show all entries
            </AppButton>
          }
          description="There are journal entries outside this period. Choose a wider range to look for connected patterns."
          title="No entries in this date range"
        />
      ) : null}

      {viewModel && viewModel.entryCount > 0 && viewModel.entryCount < 5 ? (
        <EmptyState
          action={
            <AppButton asChild variant="secondary">
              <AppLink href={routes.newEntry.path}>Add another entry</AppLink>
            </AppButton>
          }
          description="Orion needs at least five entries across several days before suggesting patterns over time."
          title="A little more history is needed"
        />
      ) : null}

      {viewModel && viewModel.entryCount >= 5 && successPanels ? (
        <ReflectionTabs
          onValueChange={setActiveView}
          panels={successPanels}
          value={activeView}
        />
      ) : null}

      <Typography aria-live="polite" className="sr-only" variant="bodySmall">
        {Object.entries(responses).map(
          ([key, response]) => `${key} feedback saved: ${response}. `,
        )}
      </Typography>

      <EvidenceDrawer
        items={drawerItems}
        onOpenChange={setDrawerOpen}
        open={drawerOpen}
      />
    </PageShell>
  );
}

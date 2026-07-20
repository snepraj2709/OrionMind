'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

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
import { useAuth } from '@/features/auth';
import { useOnlineStatus } from '@/hooks';
import type { EvidenceItem } from '@/types/evidence';

import { HiddenDriverCard } from './hidden-driver-card';
import { InnerTensionCard } from './inner-tension-card';
import type {
  ReflectionRange,
  ReflectionResponse,
  ReflectionView,
} from './model';
import { reflectionTabByView } from './model';
import { useReflectionQuery } from './queries';
import { RecurringLoop } from './recurring-loop';
import { ReflectionTabs } from './reflection-tabs';
import {
  reflectionsRepository,
  type ReflectionsRepository,
} from './repository';

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
  const { user } = useAuth();
  const [range, setRange] = useState<ReflectionRange>('all');
  const [activeView, setActiveView] =
    useState<ReflectionView>('hidden-drivers');
  const [responses, setResponses] = useState<
    Record<string, ReflectionResponse>
  >({});
  const [drawerItems, setDrawerItems] = useState<EvidenceItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isOnline = useOnlineStatus();

  const { query: reflectionQuery, viewStatus } = useReflectionQuery(
    user
      ? {
          userId: user.id,
          reflectionTab: reflectionTabByView[activeView],
          range,
        }
      : undefined,
    repository,
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

  const response = reflectionQuery.data;
  const period = response?.period;
  let activeEvidence: EvidenceItem[] = [];
  let activePanel: ReactNode = null;

  if (response?.reflectionTab === 'hiddenDriver') {
    activeEvidence = response.data.evidence;
    activePanel = (
      <HiddenDriverCard
        driver={response.data}
        onResponseChange={(nextResponse) =>
          setResponse('hidden-drivers', nextResponse)
        }
        onViewEvidence={() => openEvidence(response.data.evidence)}
        response={responses['hidden-drivers']}
      />
    );
  }

  if (response?.reflectionTab === 'recurringLoop') {
    activeEvidence = response.data.evidence;
    activePanel =
      response.data.steps.length === 0 ? (
        <NoResultsState
          description="No recurring loop was returned for the selected period."
          title="No recurring loops in this range"
        />
      ) : (
        <Section
          description={response.data.description}
          headingId="recurring-loops-heading"
          title={response.data.title}
        >
          <RecurringLoop
            loop={response.data}
            onResponseChange={(nextResponse) =>
              setResponse('recurring-loops', nextResponse)
            }
            onViewEvidence={() => openEvidence(response.data.evidence)}
            response={responses['recurring-loops']}
          />
        </Section>
      );
  }

  if (response?.reflectionTab === 'innerTension') {
    activeEvidence = response.data.tensions.flatMap(
      (tension) => tension.evidence,
    );
    activePanel =
      response.data.tensions.length === 0 ? (
        <NoResultsState
          description="No inner tension was returned for the selected period."
          title="No inner tensions in this range"
        />
      ) : (
        <Section headingId="inner-tensions-heading" title={response.data.title}>
          <div className="space-y-4">
            {response.data.tensions.map((tension) => (
              <InnerTensionCard
                key={tension.id}
                onResponseChange={(nextResponse) =>
                  setResponse(tension.id, nextResponse)
                }
                onViewEvidence={() => openEvidence(tension.evidence)}
                response={responses[tension.id]}
                tension={tension}
              />
            ))}
          </div>
        </Section>
      );
  }

  const subtitle =
    period && period.entryCount > 0 && period.from && period.to
      ? `Patterns taking shape across ${period.entryCount} entries from ${rangeDateFormatter.format(new Date(`${period.from}T00:00:00Z`))}–${rangeDateFormatter.format(new Date(`${period.to}T00:00:00Z`))}.`
      : 'A connected view of patterns across your journal history.';

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
            {period && period.entryCount >= 5 && activeEvidence.length > 0 ? (
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
              loading={reflectionQuery.isFetching}
              loadingLabel="Refreshing reflections"
              onClick={() => void reflectionQuery.refetch()}
              variant="icon"
            />
          </>
        }
        description={subtitle}
        title={routes.reflections.label}
      />

      <DataViewStatus
        initialError={dataViewMessages.reflections.initial}
        onRetry={() => void reflectionQuery.refetch()}
        refreshError={dataViewMessages.reflections.refresh}
        refreshingAriaLabel="Refreshing reflections"
        refreshingLabel="Refreshing reflections… Your current view will stay in place."
        retryDisabled={!isOnline}
        skeletonCount={1}
        status={viewStatus}
      />

      {!isOnline && reflectionQuery.data ? (
        <InlineError>
          You are offline. Orion is showing the last available reflections;
          refresh will resume when your connection returns.
        </InlineError>
      ) : null}

      {period?.entryCount === 0 && period.totalAvailable === 0 ? (
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

      {period?.entryCount === 0 && period.totalAvailable > 0 ? (
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

      {period && period.entryCount > 0 && period.entryCount < 5 ? (
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

      {period && period.entryCount >= 5 && activePanel ? (
        <ReflectionTabs
          onValueChange={(nextView) => {
            setActiveView(nextView);
            setDrawerOpen(false);
          }}
          panel={activePanel}
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

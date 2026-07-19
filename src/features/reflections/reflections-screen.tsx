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
import { routes } from '@/config/routes';
import { dataViewMessages } from '@/config/messages';
import { useOnlineStatus } from '@/hooks';
import type { EvidenceItem } from '@/types/evidence';

import { deriveReflectionViewModel } from './adapter';
import { FocusExperimentCard } from './focus-experiment-card';
import { HiddenDriverCard, type ResonanceValue } from './hidden-driver-card';
import { InnerTensionCard } from './inner-tension-card';
import { reflectionsRepository } from './mock-repository';
import type { ReflectionRange } from './model';
import { useReflectionEntriesQuery } from './queries';
import { RecurringLoop } from './recurring-loop';
import type { ReflectionsRepository } from './repository';

const rangeDateFormatter = new Intl.DateTimeFormat('en', {
  day: 'numeric',
  month: 'long',
  timeZone: 'UTC',
});

export interface ReflectionsScreenProps {
  repository?: ReflectionsRepository;
}

export function ReflectionsScreen({
  repository = reflectionsRepository,
}: ReflectionsScreenProps) {
  const [range, setRange] = useState<ReflectionRange>('30d');
  const [driverResonance, setDriverResonance] = useState<ResonanceValue>();
  const [loopFeedback, setLoopFeedback] = useState<string>();
  const [tensionResponses, setTensionResponses] = useState<
    Record<string, 'resonates' | 'rejected'>
  >({});
  const [focusResponse, setFocusResponse] = useState<string>();
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
    setDriverResonance(undefined);
    setLoopFeedback(undefined);
    setTensionResponses({});
    setFocusResponse(undefined);
    setDrawerOpen(false);
  }

  const subtitle =
    viewModel && viewModel.entryCount > 0
      ? `Patterns taking shape across ${viewModel.entryCount} entries from ${rangeDateFormatter.format(new Date(viewModel.from))}–${rangeDateFormatter.format(new Date(viewModel.to))}.`
      : 'A connected view of patterns across your journal history.';

  return (
    <PageShell className="space-y-10">
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
            />
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

      <nav aria-label="Reflection sections" className="flex flex-wrap gap-4">
        <AppLink href="#hidden-drivers">Hidden drivers</AppLink>
        <AppLink href="#recurring-loops">Recurring loops</AppLink>
        <AppLink href="#inner-tensions">Inner tensions</AppLink>
      </nav>

      <DataViewStatus
        initialError={dataViewMessages.reflections.initial}
        onRetry={() => void entriesQuery.refetch()}
        refreshError={dataViewMessages.reflections.refresh}
        refreshingAriaLabel="Refreshing reflections"
        refreshingLabel="Refreshing reflections… Your current view will stay in place."
        retryDisabled={!isOnline}
        skeletonCount={4}
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

      {viewModel && viewModel.entryCount >= 5 ? (
        <div className="space-y-16">
          <Section headingId="hidden-drivers-heading" title="Hidden drivers">
            <div id="hidden-drivers" className="scroll-mt-20">
              <HiddenDriverCard
                driver={viewModel.hiddenDriver}
                onResonanceChange={setDriverResonance}
                onViewEvidence={() =>
                  openEvidence(viewModel.hiddenDriver.evidence)
                }
                resonance={driverResonance}
              />
            </div>
          </Section>

          <Section
            description="A tentative trigger, response, and consequence cycle that appears across this period."
            headingId="recurring-loops-heading"
            title="A loop that may be keeping you stuck"
          >
            <div id="recurring-loops" className="scroll-mt-20">
              <RecurringLoop
                feedback={loopFeedback}
                loop={viewModel.loop}
                onFeedbackChange={setLoopFeedback}
                onViewEvidence={(stepIndex) =>
                  openEvidence(
                    stepIndex === undefined
                      ? viewModel.loop.evidence
                      : (viewModel.loop.steps[stepIndex]?.evidence ?? []),
                  )
                }
              />
            </div>
          </Section>

          <Section
            description="Both sides can be valid needs. The question is how they might coexist."
            headingId="inner-tensions-heading"
            title="Needs you may be trying to hold at the same time"
          >
            <div id="inner-tensions" className="scroll-mt-20 space-y-6">
              {viewModel.tensions.map((tension) => (
                <InnerTensionCard
                  key={tension.id}
                  onResponseChange={(response) =>
                    setTensionResponses((current) => ({
                      ...current,
                      [tension.id]: response,
                    }))
                  }
                  onViewEvidence={() => openEvidence(tension.evidence)}
                  response={tensionResponses[tension.id]}
                  tension={tension}
                />
              ))}
            </div>
          </Section>

          <FocusExperimentCard
            focus={viewModel.focus}
            onResponseChange={setFocusResponse}
            onViewEvidence={() => openEvidence(viewModel.focus.evidence)}
            response={focusResponse}
          />
        </div>
      ) : null}

      <Typography aria-live="polite" className="sr-only" variant="bodySmall">
        {loopFeedback ? `Loop feedback saved: ${loopFeedback}.` : null}
      </Typography>

      <EvidenceDrawer
        items={drawerItems}
        onOpenChange={setDrawerOpen}
        open={drawerOpen}
      />
    </PageShell>
  );
}

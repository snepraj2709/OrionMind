'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { AppButton } from '@/components/design-system';
import {
  DataViewStatus,
  EmptyState,
  InlineError,
  NoResultsState,
  ProcessingState,
} from '@/components/feedback';
import { PageHeader, PageShell, Section } from '@/components/layout';
import { AppLink, SegmentedControl } from '@/components/navigation';
import { EvidenceDrawer, RefreshButton } from '@/components/shared';
import type { ThemeKey } from '@/config/design-system';
import { dataViewMessages } from '@/config/messages';
import { routes } from '@/config/routes';
import { useAuth } from '@/features/auth';
import { useOnlineStatus } from '@/hooks';
import type { EvidenceItem as DrawerEvidenceItem } from '@/types/evidence';

import type {
  EvidenceItem,
  InsufficientInsight,
  ProcessingInsight,
  ReflectionFeedbackResponse,
  ReflectionRange,
  UnavailableInsight,
} from './api-schema';
import { HiddenDriverCard } from './hidden-driver-card';
import { InnerTensionCard } from './inner-tension-card';
import type { ReflectionView } from './model';
import {
  useReflectionFeedbackMutation,
  useReflectionQuery,
  useReflectionRecalculationMutation,
} from './queries';
import { RecurringLoop } from './recurring-loop';
import { ReflectionTabs } from './reflection-tabs';
import {
  reflectionsRepository,
  ReflectionRequestError,
  type ReflectionsRepository,
} from './repository';

const rangeDateFormatter = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
});

const drawerThemeByApiTheme = {
  career: 'career',
  money: 'money',
  health: 'health',
  love_life: 'loveLife',
  family_friends: 'familyAndFriends',
  personal_growth: 'personalGrowth',
  fun_recreation: 'funAndRecreation',
  home_lifestyle: 'homeAndLifestyle',
} satisfies Record<NonNullable<EvidenceItem['theme']>, ThemeKey>;

function toDrawerEvidence(item: EvidenceItem): DrawerEvidenceItem {
  return {
    id: item.id,
    date: item.entryDate,
    source: item.sourceLabel,
    text: item.quote,
    interpretation: item.interpretation,
    theme: item.theme ? drawerThemeByApiTheme[item.theme] : undefined,
    supports: item.supports,
  };
}

function InsufficientSection({ insight }: { insight: InsufficientInsight }) {
  return (
    <NoResultsState
      description={insight.message}
      title="Not enough evidence in this range"
    />
  );
}

function ProcessingSection({ insight }: { insight: ProcessingInsight }) {
  return (
    <ProcessingState
      description={insight.message}
      title="Recalculating this reflection"
    />
  );
}

function UnavailableSection({
  insight,
  onRetry,
  retryDisabled,
}: {
  insight: UnavailableInsight;
  onRetry: () => void;
  retryDisabled: boolean;
}) {
  return (
    <InlineError
      action={
        insight.retryable ? (
          <AppButton
            disabled={retryDisabled}
            onClick={onRetry}
            size="compact"
            variant="ghost"
          >
            Retry
          </AppButton>
        ) : undefined
      }
    >
      {insight.message}
    </InlineError>
  );
}

function recalculationErrorMessage(error: Error | null) {
  if (error instanceof ReflectionRequestError) {
    if (error.errorCode === 'REFLECTION_ALREADY_CURRENT') {
      return 'These reflections are already up to date.';
    }
    if (error.errorCode === 'REFLECTION_NOT_ELIGIBLE') {
      return 'There is not enough reflective evidence to recalculate these reflections yet.';
    }
  }
  return 'Orion could not start recalculating your reflections. Your last available view is still shown.';
}

function canRetryRecalculation(error: Error | null) {
  return !(
    error instanceof ReflectionRequestError &&
    (error.errorCode === 'REFLECTION_ALREADY_CURRENT' ||
      error.errorCode === 'REFLECTION_NOT_ELIGIBLE')
  );
}

function NoEvidenceSection({ range }: { range: ReflectionRange }) {
  return (
    <NoResultsState
      description={
        range === 'all'
          ? 'No supporting entries are available for this pattern in the latest 90-day reflection window.'
          : 'No supporting entries for this pattern fall within the selected range. Try a broader range.'
      }
      title="No supporting entries in this range"
    />
  );
}

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
  const [drawerItems, setDrawerItems] = useState<DrawerEvidenceItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isOnline = useOnlineStatus();
  const activeUserId = user?.id;

  const {
    pollingExhausted,
    query: reflectionQuery,
    resetPolling,
    retryPolling,
    viewStatus,
  } = useReflectionQuery(activeUserId, { range }, repository);
  const recalculation = useReflectionRecalculationMutation(
    activeUserId,
    range,
    resetPolling,
    repository,
  );
  const feedbackMutation = useReflectionFeedbackMutation(
    activeUserId,
    range,
    repository,
    resetPolling,
  );

  function openEvidence(items: EvidenceItem[]) {
    setDrawerItems(items.map(toDrawerEvidence));
    setDrawerOpen(true);
  }

  function handleRangeChange(nextRange: ReflectionRange) {
    setRange(nextRange);
    setDrawerOpen(false);
  }

  function submitFeedback(
    insightId: string,
    response: ReflectionFeedbackResponse,
  ) {
    const snapshotId = reflectionQuery.data?.snapshot?.id;
    if (!snapshotId) return;
    feedbackMutation.submitFeedback({ insightId, response, snapshotId });
  }

  const response = reflectionQuery.data;
  const basis = response?.analysisBasis;
  const isProcessing =
    response?.processingState === 'pending' ||
    response?.data.hiddenDriver.status === 'processing' ||
    response?.data.recurringLoop.status === 'processing' ||
    response?.data.innerTensions.status === 'processing';
  const recalculationBusy = recalculation.isPending || isProcessing;

  function requestRecalculation() {
    if (!isOnline || recalculationBusy) return;
    recalculation.mutate();
  }

  let activePanel: ReactNode = null;

  if (response && activeView === 'hidden-drivers') {
    const insight = response.data.hiddenDriver;
    activePanel =
      insight.status === 'processing' ? (
        <ProcessingSection insight={insight} />
      ) : insight.status === 'insufficient_evidence' ? (
        <InsufficientSection insight={insight} />
      ) : insight.status === 'unavailable' ? (
        <UnavailableSection
          insight={insight}
          onRetry={requestRecalculation}
          retryDisabled={!isOnline || recalculationBusy}
        />
      ) : insight.evidence.length === 0 ? (
        <NoEvidenceSection range={range} />
      ) : (
        <HiddenDriverCard
          driver={insight}
          error={feedbackMutation.errors[insight.id]}
          onResponseChange={(nextResponse) =>
            submitFeedback(insight.id, nextResponse)
          }
          onViewEvidence={() => openEvidence(insight.evidence)}
          pending={feedbackMutation.pendingInsightIds.has(insight.id)}
          response={insight.feedback}
        />
      );
  }

  if (response && activeView === 'recurring-loops') {
    const insight = response.data.recurringLoop;
    activePanel =
      insight.status === 'processing' ? (
        <ProcessingSection insight={insight} />
      ) : insight.status === 'insufficient_evidence' ? (
        <InsufficientSection insight={insight} />
      ) : insight.status === 'unavailable' ? (
        <UnavailableSection
          insight={insight}
          onRetry={requestRecalculation}
          retryDisabled={!isOnline || recalculationBusy}
        />
      ) : insight.evidence.length === 0 ? (
        <NoEvidenceSection range={range} />
      ) : (
        <Section
          description={insight.description}
          headingId="recurring-loops-heading"
          title={insight.title}
        >
          <RecurringLoop
            error={feedbackMutation.errors[insight.id]}
            loop={insight}
            onResponseChange={(nextResponse) =>
              submitFeedback(insight.id, nextResponse)
            }
            onViewEvidence={() => openEvidence(insight.evidence)}
            pending={feedbackMutation.pendingInsightIds.has(insight.id)}
            response={insight.feedback}
          />
        </Section>
      );
  }

  if (response && activeView === 'inner-tensions') {
    const insight = response.data.innerTensions;
    const tensionsWithEvidence =
      insight.status === 'available'
        ? insight.tensions.filter((tension) => tension.evidence.length > 0)
        : [];
    activePanel =
      insight.status === 'processing' ? (
        <ProcessingSection insight={insight} />
      ) : insight.status === 'insufficient_evidence' ? (
        <InsufficientSection insight={insight} />
      ) : insight.status === 'unavailable' ? (
        <UnavailableSection
          insight={insight}
          onRetry={requestRecalculation}
          retryDisabled={!isOnline || recalculationBusy}
        />
      ) : tensionsWithEvidence.length === 0 ? (
        <NoEvidenceSection range={range} />
      ) : (
        <Section
          headingId="inner-tensions-heading"
          title="Needs you may be trying to hold at the same time"
        >
          <div className="space-y-4">
            {tensionsWithEvidence.map((tension) => (
              <InnerTensionCard
                error={feedbackMutation.errors[tension.id]}
                key={tension.id}
                onResponseChange={(nextResponse) =>
                  submitFeedback(tension.id, nextResponse)
                }
                onViewEvidence={() => openEvidence(tension.evidence)}
                pending={feedbackMutation.pendingInsightIds.has(tension.id)}
                response={tension.feedback}
                tension={tension}
              />
            ))}
          </div>
        </Section>
      );
  }

  let subtitle =
    'A connected view of patterns within your latest 90-day reflection window.';
  if (basis?.currentRangeFrom && basis.currentRangeTo) {
    const dates = `${rangeDateFormatter.format(new Date(`${basis.currentRangeFrom}T00:00:00Z`))}–${rangeDateFormatter.format(new Date(`${basis.currentRangeTo}T00:00:00Z`))}`;
    subtitle =
      range === 'all'
        ? `Patterns taking shape across ${basis.validEntryCount} reflective ${basis.validEntryCount === 1 ? 'entry' : 'entries'} in your latest 90-day reflection window (${dates}).`
        : `Patterns shown for ${dates}, drawn from your latest 90-day reflection window.`;
  }

  const showTabs =
    viewStatus === 'loading' ||
    (response !== undefined &&
      response.reflectionState !== 'insufficient_reflective_content');

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
                { label: 'Latest 90 days', value: 'all' },
              ]}
              onValueChange={(value) =>
                handleRangeChange(value as ReflectionRange)
              }
              value={range}
              variant="strong"
            />
            <RefreshButton
              aria-label="Refresh reflections"
              disabled={!isOnline || recalculationBusy}
              loading={reflectionQuery.isFetching || recalculationBusy}
              loadingLabel="Recalculating reflections"
              onClick={requestRecalculation}
              variant="icon"
            />
          </>
        }
        description={subtitle}
        title={routes.reflections.label}
      />

      <DataViewStatus
        initialError={dataViewMessages.reflections.initial}
        onRetry={() => void retryPolling()}
        refreshError={dataViewMessages.reflections.refresh}
        refreshingAriaLabel="Refreshing reflections"
        refreshingLabel="Refreshing reflections… Your current view will stay in place."
        retryDisabled={!isOnline}
        skeletonCount={1}
        status={viewStatus}
      />

      {!isOnline && response ? (
        <InlineError>
          You are offline. Orion is showing the last available reflections;
          refresh will resume when your connection returns.
        </InlineError>
      ) : null}

      {recalculation.isError ? (
        <InlineError
          action={
            canRetryRecalculation(recalculation.error) ? (
              <AppButton
                disabled={!isOnline || recalculation.isPending}
                onClick={requestRecalculation}
                size="compact"
                variant="ghost"
              >
                Retry
              </AppButton>
            ) : undefined
          }
        >
          {recalculationErrorMessage(recalculation.error)}
        </InlineError>
      ) : null}

      {pollingExhausted && !reflectionQuery.isError ? (
        <InlineError
          action={
            <AppButton
              disabled={!isOnline || reflectionQuery.isFetching}
              loading={reflectionQuery.isFetching}
              loadingLabel="Checking reflections"
              onClick={() => void retryPolling()}
              size="compact"
              variant="ghost"
            >
              Check again
            </AppButton>
          }
        >
          This update is taking longer than expected. Check again without
          starting another recalculation.
        </InlineError>
      ) : null}

      {response?.reflectionState === 'first_reflection_pending' ? (
        <ProcessingState
          description="Orion is looking across your reflective entries. You can keep journaling while this finishes."
          title="Your first reflection is taking shape"
        />
      ) : null}

      {response?.reflectionState === 'stale' &&
      response.processingState === 'pending' ? (
        <ProcessingState
          description="Your last reflection remains available while Orion considers newer entries."
          title="Updating your reflections"
        />
      ) : null}

      {response?.reflectionState === 'stale' &&
      response.processingState === 'failed' ? (
        <InlineError
          action={
            <AppButton
              disabled={!isOnline}
              onClick={requestRecalculation}
              size="compact"
              variant="ghost"
            >
              Retry
            </AppButton>
          }
        >
          Orion could not refresh these reflections. The last successful view is
          still shown.
        </InlineError>
      ) : null}

      {response?.reflectionState === 'insufficient_reflective_content' ? (
        <EmptyState
          action={
            <AppButton asChild variant="secondary">
              <AppLink href={routes.newEntry.path}>Write a new entry</AppLink>
            </AppButton>
          }
          description={
            response.data.hiddenDriver.status === 'insufficient_evidence'
              ? response.data.hiddenDriver.message
              : 'There is not enough personal reflection to identify a meaningful pattern yet.'
          }
          title="More personal reflection is needed"
        />
      ) : null}

      {showTabs ? (
        <ReflectionTabs
          onValueChange={(nextView) => {
            setActiveView(nextView);
            setDrawerOpen(false);
          }}
          panel={activePanel}
          value={activeView}
        />
      ) : null}

      <EvidenceDrawer
        items={drawerItems}
        onOpenChange={setDrawerOpen}
        open={drawerOpen}
      />
    </PageShell>
  );
}

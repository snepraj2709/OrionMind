'use client';

import { useMemo, useState } from 'react';

import { Surface } from '@/components/cards';
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
import { formatLongDate } from '@/lib/date';
import { useOnlineStatus } from '@/hooks';
import { useAuth } from '@/features/auth';
import type { EvidenceItem } from '@/types/evidence';

import { deriveJourneyViewModel } from './adapter';
import { ChapterDetail } from './chapter-detail';
import { ChapterRail } from './chapter-rail';
import { LockedJourney } from './locked-journey';
import { MockJourneyRepository } from './mock-repository';
import type { JourneyBoundary, JourneyRange } from './model';
import { useJourneyEntriesQuery } from './queries';
import type { JourneyRepository } from './repository';
import { ThemeRiver } from './theme-river';

const fixedJourneyRepository = new MockJourneyRepository();

export interface JourneyScreenProps {
  repository?: JourneyRepository;
}

export function JourneyScreen({
  repository = fixedJourneyRepository,
}: JourneyScreenProps) {
  const { user } = useAuth();
  const [range, setRange] = useState<JourneyRange>('all');
  const [selectedChapterId, setSelectedChapterId] = useState<string>();
  const [chapterNameOverrides, setChapterNameOverrides] = useState<
    Record<string, string>
  >({});
  const [drawerItems, setDrawerItems] = useState<EvidenceItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isOnline = useOnlineStatus();
  const {
    journeyQuery: entriesQuery,
    statusQuery,
    viewStatus,
  } = useJourneyEntriesQuery(range, user?.id, repository);
  const viewModel = useMemo(
    () =>
      entriesQuery.data
        ? deriveJourneyViewModel(entriesQuery.data.entries, range)
        : undefined,
    [entriesQuery.data, range],
  );
  const chapters = useMemo(
    () =>
      viewModel?.chapters.map((chapter) => ({
        ...chapter,
        title: chapterNameOverrides[chapter.id] ?? chapter.title,
      })) ?? [],
    [chapterNameOverrides, viewModel?.chapters],
  );
  const selectedChapter =
    chapters.find((chapter) => chapter.id === selectedChapterId) ??
    chapters.at(-1);
  const hasThemeData =
    viewModel?.streamData.some((point) =>
      Object.values(point.values).some((value) => value > 0),
    ) ?? false;

  function openEvidence(items: EvidenceItem[]) {
    setDrawerItems(items);
    setDrawerOpen(true);
  }

  function handleBoundaryEvidence(boundary: JourneyBoundary) {
    openEvidence(boundary.evidence);
  }

  return (
    <PageShell className="space-y-12">
      <PageHeader
        actions={
          <>
            <SegmentedControl
              ariaLabel="Journey date range"
              density="compact"
              items={[
                { label: '6M', value: '6m' },
                { label: '1Y', value: '1y' },
                { label: '2Y', value: '2y' },
                { label: '3Y', value: '3y' },
                { label: '5Y', value: '5y' },
                { label: 'All', value: 'all' },
              ]}
              onValueChange={(value) => {
                setRange(value as JourneyRange);
                setSelectedChapterId(undefined);
              }}
              value={range}
              variant="strong"
            />
            {statusQuery.data?.enabled ? (
              <RefreshButton
                aria-label="Refresh journey"
                disabled={!isOnline}
                loading={entriesQuery.isFetching}
                loadingLabel="Refreshing journey"
                onClick={() => void entriesQuery.refetch()}
                variant="icon"
              />
            ) : null}
          </>
        }
        description="See how your attention, priorities and sense of self have changed over time."
        title="Your Journey"
      />

      <DataViewStatus
        initialError={dataViewMessages.journey.initial}
        onRetry={() =>
          void Promise.all([entriesQuery.refetch(), statusQuery.refetch()])
        }
        refreshError={dataViewMessages.journey.refresh}
        retryDisabled={!isOnline}
        status={viewStatus}
      />

      {!isOnline && entriesQuery.data ? (
        <InlineError>
          You are offline. Orion is showing the last available journey view.
        </InlineError>
      ) : null}

      {statusQuery.data && !statusQuery.data.enabled && entriesQuery.data ? (
        <LockedJourney
          status={statusQuery.data}
          stream={entriesQuery.data.stream}
        />
      ) : null}

      {statusQuery.data?.enabled &&
      viewModel?.entryCount === 0 &&
      entriesQuery.data?.totalAvailable === 0 ? (
        <EmptyState
          action={
            <AppButton asChild>
              <AppLink href={routes.newEntry.path}>
                Write your first entry
              </AppLink>
            </AppButton>
          }
          description="Chapters and theme movement begin to appear as your journal history grows."
          title="Your journey is ready to begin"
        />
      ) : null}

      {statusQuery.data?.enabled &&
      viewModel?.entryCount === 0 &&
      (entriesQuery.data?.totalAvailable ?? 0) > 0 ? (
        <NoResultsState
          action={
            <AppButton onClick={() => setRange('all')} variant="secondary">
              Show all entries
            </AppButton>
          }
          description="There are journal entries outside this period. Choose a wider range to explore your longer story."
          title="No entries in this date range"
        />
      ) : null}

      {statusQuery.data?.enabled &&
      viewModel &&
      viewModel.entryCount > 0 &&
      viewModel.entryCount < 5 ? (
        <EmptyState
          action={
            <AppButton asChild variant="secondary">
              <AppLink href={routes.newEntry.path}>Add another entry</AppLink>
            </AppButton>
          }
          description="Orion needs at least five entries before showing a responsible longitudinal view."
          title="A little more history is needed"
        />
      ) : null}

      {statusQuery.data?.enabled && viewModel && viewModel.entryCount >= 5 ? (
        <div className="space-y-16">
          <section
            aria-label="Journey coverage"
            className="border-border grid gap-4 border-y py-4 sm:grid-cols-2 xl:grid-cols-5"
          >
            {[
              ['Entries', String(viewModel.entryCount)],
              ['From', formatLongDate(viewModel.from)],
              ['To', formatLongDate(viewModel.to)],
              ['Chapters', String(chapters.length)],
              ['Coverage', viewModel.coverageLabel],
            ].map(([label, value]) => (
              <div className="space-y-2" key={label}>
                <Typography variant="eyebrow">{label}</Typography>
                <Typography variant="metadata">{value}</Typography>
              </div>
            ))}
          </section>

          <Surface className="gap-3 p-6">
            <Typography variant="eyebrow">Across this period</Typography>
            <Typography
              as="p"
              className="text-measure-wide"
              variant="reflectiveStatement"
            >
              {viewModel.summary}
            </Typography>
          </Surface>

          {hasThemeData ? (
            <ThemeRiver
              boundaries={viewModel.boundaries}
              chapters={chapters}
              onSelectChapter={setSelectedChapterId}
              onViewEvidence={handleBoundaryEvidence}
              points={viewModel.streamData}
              selectedChapterId={selectedChapter?.id}
            />
          ) : (
            <EmptyState
              description="Entries exist in this period, but not enough include ranked themes to draw a responsible longitudinal view."
              title="Not enough theme data for the river"
            />
          )}

          <Section
            description="Select a chapter to explore the evidence and interpretation behind it."
            headingId="chapters-heading"
            title={
              chapters.length > 1
                ? `${chapters.length} chapters detected`
                : chapters.length === 1
                  ? 'A chapter is emerging'
                  : 'No chapters detected yet'
            }
          >
            {chapters.length > 0 ? (
              <ChapterRail
                chapters={chapters}
                onSelectChapter={setSelectedChapterId}
                selectedChapterId={selectedChapter?.id}
              />
            ) : (
              <EmptyState
                description="Orion has not found a sustained change across enough themed entries to propose a chapter boundary."
                title="No chapter boundary yet"
              />
            )}
          </Section>

          {selectedChapter ? (
            <ChapterDetail
              key={selectedChapter.id}
              chapter={selectedChapter}
              onRenameChapter={(title) =>
                setChapterNameOverrides((current) => ({
                  ...current,
                  [selectedChapter.id]: title,
                }))
              }
              onViewEvidence={(items) =>
                openEvidence(items ?? selectedChapter.evidence)
              }
            />
          ) : null}
        </div>
      ) : null}

      <Typography aria-live="polite" className="sr-only" variant="bodySmall">
        {selectedChapter ? `${selectedChapter.title} selected.` : null}
      </Typography>
      <EvidenceDrawer
        items={drawerItems}
        onOpenChange={setDrawerOpen}
        open={drawerOpen}
      />
    </PageShell>
  );
}

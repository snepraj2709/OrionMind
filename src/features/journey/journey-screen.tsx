'use client';

import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Surface } from '@/components/cards';
import { AppButton, Typography } from '@/components/design-system';
import {
  EmptyState,
  InlineError,
  NoResultsState,
  PageErrorState,
  SkeletonList,
} from '@/components/feedback';
import { PageHeader, PageShell, Section } from '@/components/layout';
import { AppLink, SegmentedControl } from '@/components/navigation';
import { EvidenceDrawer } from '@/components/shared';
import { routes } from '@/config/routes';
import { formatLongDate } from '@/lib/date';
import { useOnlineStatus } from '@/hooks';
import type { EvidenceItem } from '@/types/evidence';

import { deriveJourneyViewModel } from './adapter';
import { ChapterDetail } from './chapter-detail';
import { ChapterRail } from './chapter-rail';
import { journeyRepository } from './mock-repository';
import type { JourneyBoundary, JourneyRange } from './model';
import type { JourneyRepository } from './repository';
import { ThemeRiver } from './theme-river';

export interface JourneyScreenProps {
  repository?: JourneyRepository;
}

export function JourneyScreen({
  repository = journeyRepository,
}: JourneyScreenProps) {
  const [range, setRange] = useState<JourneyRange>('2y');
  const [selectedChapterId, setSelectedChapterId] = useState<string>();
  const [chapterNameOverrides, setChapterNameOverrides] = useState<
    Record<string, string>
  >({});
  const [drawerItems, setDrawerItems] = useState<EvidenceItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isOnline = useOnlineStatus();
  const entriesQuery = useQuery({
    queryKey: ['journey', range],
    queryFn: () => repository.getJourneyEntries(range),
  });
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
            />
            <AppButton
              aria-label="Refresh journey"
              disabled={!isOnline}
              loading={entriesQuery.isFetching}
              loadingLabel="Refreshing journey"
              onClick={() => void entriesQuery.refetch()}
              variant="icon"
            >
              <RefreshCw aria-hidden="true" className="size-4" />
            </AppButton>
          </>
        }
        description="See how your attention, priorities and sense of self have changed over time."
        title="Your Journey"
      />

      {entriesQuery.isPending ? <SkeletonList count={5} /> : null}

      {entriesQuery.isError && !entriesQuery.data ? (
        <PageErrorState
          action={
            <AppButton
              onClick={() => void entriesQuery.refetch()}
              variant="secondary"
            >
              Retry
            </AppButton>
          }
          description="Orion could not assemble your journey history. Your original entries are unchanged."
          title="Your journey is unavailable"
        />
      ) : null}

      {entriesQuery.isFetching && !entriesQuery.isPending ? (
        <Typography
          aria-label="Refreshing journey"
          aria-live="polite"
          className="text-muted-foreground"
          role="status"
          variant="metadata"
        >
          Refreshing your journey… The current view will stay in place.
        </Typography>
      ) : null}

      {!isOnline && entriesQuery.data ? (
        <InlineError>
          You are offline. Orion is showing the last available journey view.
        </InlineError>
      ) : null}

      {entriesQuery.isError && entriesQuery.data ? (
        <InlineError
          action={
            <AppButton
              disabled={!isOnline}
              onClick={() => void entriesQuery.refetch()}
              size="compact"
              variant="ghost"
            >
              Retry
            </AppButton>
          }
        >
          New journey data could not be loaded. Showing the last available view.
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
          description="Chapters and theme movement begin to appear as your journal history grows."
          title="Your journey is ready to begin"
        />
      ) : null}

      {viewModel?.entryCount === 0 &&
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

      {viewModel && viewModel.entryCount > 0 && viewModel.entryCount < 5 ? (
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

      {viewModel && viewModel.entryCount >= 5 ? (
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
              variant="reflectionCardStatement"
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

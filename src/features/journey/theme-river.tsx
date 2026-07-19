'use client';

import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react';
import { useState } from 'react';

import { Surface } from '@/components/cards';
import { ThemeBadge } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import { themeRegistry, type ThemeKey } from '@/config/design-system';

import type { JourneyBoundary, JourneyChapter, ThemeRiverPoint } from './model';

const themeKeys = Object.keys(themeRegistry) as ThemeKey[];

function joinThemeNames(keys: ThemeKey[]) {
  return keys.map((key) => themeRegistry[key].label).join(', ');
}

type ThemeStyle = CSSProperties & { '--theme-color': string };

function areaPath(
  points: ThemeRiverPoint[],
  key: ThemeKey,
  priorKeys: ThemeKey[],
) {
  if (points.length === 0) return '';
  const width = 1000;
  const top = points.map((point, index) => {
    const x =
      points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
    const prior = priorKeys.reduce(
      (sum, priorKey) => sum + point.values[priorKey],
      0,
    );
    return [x, 240 - (prior + point.values[key]) * 200] as const;
  });
  const bottom = [...points].reverse().map((point, reverseIndex) => {
    const index = points.length - reverseIndex - 1;
    const x =
      points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
    const prior = priorKeys.reduce(
      (sum, priorKey) => sum + point.values[priorKey],
      0,
    );
    return [x, 240 - prior * 200] as const;
  });
  return `M ${top.map(([x, y]) => `${x} ${y}`).join(' L ')} L ${bottom
    .map(([x, y]) => `${x} ${y}`)
    .join(' L ')} Z`;
}

function indexForDate(points: ThemeRiverPoint[], date: string) {
  const exact = points.findIndex((point) => point.bucket >= date);
  return exact < 0 ? points.length - 1 : exact;
}

export interface ThemeRiverProps {
  points: ThemeRiverPoint[];
  chapters: JourneyChapter[];
  boundaries: JourneyBoundary[];
  selectedChapterId?: string;
  onSelectChapter: (chapterId: string) => void;
  onViewEvidence: (boundary: JourneyBoundary) => void;
}

export function ThemeRiver({
  boundaries,
  chapters,
  onSelectChapter,
  onViewEvidence,
  points,
  selectedChapterId,
}: ThemeRiverProps) {
  const [isolatedTheme, setIsolatedTheme] = useState<ThemeKey>();
  const [selectedBoundaryId, setSelectedBoundaryId] = useState<string>();
  const [activePointIndex, setActivePointIndex] = useState<number>();
  const [dragStartIndex, setDragStartIndex] = useState<number>();
  const [dragEndIndex, setDragEndIndex] = useState<number>();
  const [isDragging, setIsDragging] = useState(false);
  const selectedBoundary = boundaries.find(
    (boundary) => boundary.id === selectedBoundaryId,
  );
  const selectedChapter = chapters.find(
    (chapter) => chapter.id === selectedChapterId,
  );
  const selectedThemeKeys = new Set(
    selectedChapter?.themes.map((theme) => theme.key) ?? [],
  );
  const activePoint =
    activePointIndex === undefined ? undefined : points[activePointIndex];
  const inspectedRange =
    dragStartIndex === undefined || dragEndIndex === undefined
      ? undefined
      : ([
          Math.min(dragStartIndex, dragEndIndex),
          Math.max(dragStartIndex, dragEndIndex),
        ] as const);

  function pointIndexForPointer(event: ReactPointerEvent<SVGRectElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(
      1,
      Math.max(0, (event.clientX - bounds.left) / bounds.width),
    );
    return Math.min(points.length - 1, Math.round(ratio * (points.length - 1)));
  }

  function selectChapterForPoint(index: number) {
    const date = points[index]?.bucket;
    if (!date) return;
    const chapter = chapters.find(
      (candidate) =>
        candidate.start <= date && (!candidate.end || candidate.end >= date),
    );
    if (chapter) onSelectChapter(chapter.id);
  }

  return (
    <Surface className="gap-6 p-6">
      <div className="space-y-2">
        <Typography as="h2" variant="sectionTitle">
          Life Theme River
        </Typography>
        <Typography className="text-muted-foreground" variant="bodySmall">
          Theme size represents its relative presence in your entries.
        </Typography>
      </div>

      <div className="max-w-full overflow-x-auto pb-2">
        <div className="flex min-w-max gap-2" aria-label="Theme legend">
          {themeKeys.map((key) => {
            const config = themeRegistry[key];
            const style: ThemeStyle = { '--theme-color': config.color };
            return (
              <AppButton
                aria-pressed={isolatedTheme === key}
                key={key}
                onClick={() =>
                  setIsolatedTheme((current) =>
                    current === key ? undefined : key,
                  )
                }
                size="compact"
                style={style}
                variant="ghost"
              >
                <span
                  aria-hidden="true"
                  className="radius-control size-3 bg-(--theme-color)"
                />
                {config.label}
              </AppButton>
            );
          })}
        </div>
      </div>

      <div className="max-w-full overflow-x-auto">
        <div className="h-80 min-w-2xl">
          <svg
            aria-label="Relative theme presence across the selected period"
            className="h-full w-full"
            preserveAspectRatio="none"
            role="img"
            viewBox="0 0 1000 280"
          >
            {chapters.map((chapter) => {
              const start = indexForDate(points, chapter.start);
              const end = chapter.end
                ? indexForDate(points, chapter.end)
                : points.length - 1;
              const x =
                points.length > 1 ? (start / (points.length - 1)) * 1000 : 0;
              const endX =
                points.length > 1 ? (end / (points.length - 1)) * 1000 : 1000;
              return (
                <rect
                  fill="var(--muted)"
                  height="220"
                  key={chapter.id}
                  onClick={() => onSelectChapter(chapter.id)}
                  opacity={selectedChapterId === chapter.id ? 0.72 : 0.28}
                  width={Math.max(8, endX - x)}
                  x={x}
                  y="20"
                />
              );
            })}

            {themeKeys.map((key, index) => {
              const dimmedByLegend =
                isolatedTheme !== undefined && isolatedTheme !== key;
              const dimmedByChapter =
                selectedChapter !== undefined && !selectedThemeKeys.has(key);
              return (
                <path
                  d={areaPath(points, key, themeKeys.slice(0, index))}
                  fill={themeRegistry[key].color}
                  key={key}
                  opacity={dimmedByLegend || dimmedByChapter ? 0.16 : 0.82}
                  stroke={themeRegistry[key].color}
                  strokeWidth="1"
                />
              );
            })}

            {selectedChapterId
              ? chapters
                  .filter((chapter) => chapter.id !== selectedChapterId)
                  .map((chapter) => {
                    const start = indexForDate(points, chapter.start);
                    const end = chapter.end
                      ? indexForDate(points, chapter.end)
                      : points.length - 1;
                    const x =
                      points.length > 1
                        ? (start / (points.length - 1)) * 1000
                        : 0;
                    const endX =
                      points.length > 1
                        ? (end / (points.length - 1)) * 1000
                        : 1000;
                    return (
                      <rect
                        fill="var(--background)"
                        height="220"
                        key={`dim-${chapter.id}`}
                        opacity="0.38"
                        width={Math.max(8, endX - x)}
                        x={x}
                        y="20"
                      />
                    );
                  })
              : null}

            {inspectedRange ? (
              <rect
                fill="var(--primary)"
                height="220"
                opacity="0.12"
                width={
                  ((inspectedRange[1] - inspectedRange[0] + 1) /
                    Math.max(1, points.length)) *
                  1000
                }
                x={(inspectedRange[0] / Math.max(1, points.length)) * 1000}
                y="20"
              />
            ) : null}

            <rect
              aria-label="Explore the theme river. Use left and right arrow keys to inspect periods, or drag to inspect a smaller range."
              fill="transparent"
              height="220"
              onKeyDown={(event) => {
                const current = activePointIndex ?? 0;
                if (event.key === 'ArrowRight') {
                  event.preventDefault();
                  setActivePointIndex(Math.min(points.length - 1, current + 1));
                } else if (event.key === 'ArrowLeft') {
                  event.preventDefault();
                  setActivePointIndex(Math.max(0, current - 1));
                } else if (event.key === 'Home') {
                  event.preventDefault();
                  setActivePointIndex(0);
                } else if (event.key === 'End') {
                  event.preventDefault();
                  setActivePointIndex(points.length - 1);
                } else if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  selectChapterForPoint(current);
                } else if (event.key === 'Escape') {
                  setDragStartIndex(undefined);
                  setDragEndIndex(undefined);
                }
              }}
              onPointerDown={(event) => {
                const index = pointIndexForPointer(event);
                event.currentTarget.setPointerCapture(event.pointerId);
                setActivePointIndex(index);
                setDragStartIndex(index);
                setDragEndIndex(index);
                setIsDragging(true);
              }}
              onPointerLeave={() => {
                if (!isDragging) setActivePointIndex(undefined);
              }}
              onPointerMove={(event) => {
                const index = pointIndexForPointer(event);
                setActivePointIndex(index);
                if (isDragging) setDragEndIndex(index);
              }}
              onPointerUp={(event) => {
                const index = pointIndexForPointer(event);
                setActivePointIndex(index);
                setDragEndIndex(index);
                if (
                  dragStartIndex === undefined ||
                  Math.abs(index - dragStartIndex) < 1
                ) {
                  selectChapterForPoint(index);
                }
                setIsDragging(false);
                event.currentTarget.releasePointerCapture(event.pointerId);
              }}
              role="button"
              tabIndex={0}
              width="1000"
              x="0"
              y="20"
            />

            {chapters.map((chapter) => {
              const start = indexForDate(points, chapter.start);
              const x =
                points.length > 1
                  ? (start / (points.length - 1)) * 1000 + 8
                  : 8;
              return (
                <g key={`label-${chapter.id}`} pointerEvents="none">
                  <text
                    className="type-eyebrow"
                    fill="var(--foreground)"
                    x={x}
                    y="38"
                  >
                    {chapter.title}
                  </text>
                  <text
                    className="type-eyebrow"
                    fill="var(--muted-foreground)"
                    x={x}
                    y="56"
                  >
                    {chapter.status}
                  </text>
                </g>
              );
            })}

            {boundaries.map((boundary) => {
              const index = indexForDate(points, boundary.date);
              const x =
                points.length > 1 ? (index / (points.length - 1)) * 1000 : 500;
              return (
                <g
                  aria-label={`Chapter boundary on ${boundary.date}`}
                  aria-pressed={selectedBoundaryId === boundary.id}
                  className="cursor-pointer focus:outline-none"
                  key={boundary.id}
                  onClick={() => setSelectedBoundaryId(boundary.id)}
                  onFocus={() => setSelectedBoundaryId(boundary.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setSelectedBoundaryId(boundary.id);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <line
                    stroke="var(--foreground)"
                    strokeDasharray="5 5"
                    strokeWidth={selectedBoundaryId === boundary.id ? 3 : 2}
                    x1={x}
                    x2={x}
                    y1="12"
                    y2="248"
                  />
                  <circle
                    cx={x}
                    cy="18"
                    fill="var(--card)"
                    r="7"
                    stroke="var(--foreground)"
                  />
                </g>
              );
            })}

            {[points[0], points[Math.floor(points.length / 2)], points.at(-1)]
              .filter(Boolean)
              .map((point, index) => (
                <text
                  className="type-eyebrow"
                  fill="var(--muted-foreground)"
                  key={`${point!.bucket}-${index}`}
                  textAnchor={
                    index === 0 ? 'start' : index === 2 ? 'end' : 'middle'
                  }
                  x={index === 0 ? 0 : index === 2 ? 1000 : 500}
                  y="272"
                >
                  {point!.bucket}
                </text>
              ))}
          </svg>
        </div>
      </div>

      {activePoint ? (
        <Surface
          aria-live="polite"
          className="bg-muted gap-4 p-4"
          role="status"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Typography as="h3" variant="componentTitle">
              {activePoint.bucket}
            </Typography>
            <Typography className="text-muted-foreground" variant="metadata">
              {activePoint.entryCount}{' '}
              {activePoint.entryCount === 1 ? 'entry' : 'entries'}
            </Typography>
          </div>
          <div className="flex flex-wrap gap-2">
            {themeKeys
              .filter((key) => activePoint.values[key] > 0)
              .sort(
                (left, right) =>
                  activePoint.values[right] - activePoint.values[left],
              )
              .slice(0, 3)
              .map((key) => (
                <ThemeBadge key={key} theme={key} />
              ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Typography className="text-muted-foreground" variant="bodySmall">
              Rising:{' '}
              {activePoint.rising.length > 0
                ? joinThemeNames(activePoint.rising)
                : 'No clear rise in this bucket'}
            </Typography>
            <Typography className="text-muted-foreground" variant="bodySmall">
              Fading:{' '}
              {activePoint.fading.length > 0
                ? joinThemeNames(activePoint.fading)
                : 'No clear fade in this bucket'}
            </Typography>
          </div>
          <div className="border-border space-y-2 border-t pt-4">
            <Typography variant="eyebrow">
              Representative journal sentence
            </Typography>
            <Typography as="blockquote" variant="journalExcerpt">
              {activePoint.representativeSentence}
            </Typography>
          </div>
        </Surface>
      ) : null}

      {inspectedRange && inspectedRange[0] !== inspectedRange[1] ? (
        <div
          aria-live="polite"
          className="flex flex-wrap items-center justify-between gap-3"
          role="status"
        >
          <Typography className="text-muted-foreground" variant="metadata">
            Inspecting {points[inspectedRange[0]]?.bucket}–
            {points[inspectedRange[1]]?.bucket}
          </Typography>
          <AppButton
            onClick={() => {
              setDragStartIndex(undefined);
              setDragEndIndex(undefined);
            }}
            size="compact"
            variant="ghost"
          >
            Reset inspected range
          </AppButton>
        </div>
      ) : null}

      {selectedBoundary ? (
        <Surface className="bg-muted space-y-4 p-4" role="status">
          <Typography as="h3" variant="componentTitle">
            Why Orion detected a new chapter
          </Typography>
          <ul className="type-body-small list-disc space-y-2 pl-6">
            {selectedBoundary.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <Typography className="text-muted-foreground" variant="metadata">
            Based on {selectedBoundary.entryCount} entries around{' '}
            {selectedBoundary.date}.
          </Typography>
          <AppButton
            onClick={() => onViewEvidence(selectedBoundary)}
            size="compact"
            variant="link"
          >
            View supporting evidence
          </AppButton>
        </Surface>
      ) : null}

      <details>
        <summary className="type-button radius-control min-touch-target focus-visible:ring-ring cursor-pointer focus-visible:ring-2 focus-visible:outline-none">
          View data table
        </summary>
        <div className="mt-4 max-w-full overflow-x-auto">
          <table className="type-body-small w-full border-collapse text-left">
            <caption className="sr-only">
              Relative theme presence by period
            </caption>
            <thead>
              <tr className="border-border border-b">
                <th className="p-2" scope="col">
                  Period
                </th>
                {themeKeys.map((key) => (
                  <th className="p-2" key={key} scope="col">
                    {themeRegistry[key].label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr className="border-border border-b" key={point.bucket}>
                  <th className="p-2" scope="row">
                    {point.bucket}
                  </th>
                  {themeKeys.map((key) => (
                    <td className="p-2" key={key}>
                      {Math.round(point.values[key] * 100)}%
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Surface>
  );
}

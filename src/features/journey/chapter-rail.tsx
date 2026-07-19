'use client';

import { ArrowRight, Sparkles } from 'lucide-react';

import { StatusBadge, ThemeBadge } from '@/components/data-display';
import { Typography } from '@/components/design-system';
import { journeyChapterStatusPresentation } from '@/config/status';
import { formatLongDate } from '@/lib/date';
import { cn } from '@/lib/utils';

import type { JourneyChapter } from './model';

export interface ChapterRailProps {
  chapters: JourneyChapter[];
  selectedChapterId?: string;
  onSelectChapter: (chapterId: string) => void;
}

export function ChapterRail({
  chapters,
  onSelectChapter,
  selectedChapterId,
}: ChapterRailProps) {
  return (
    <div className="max-w-full overflow-x-auto pb-2">
      <div className="flex min-w-max items-stretch gap-4">
        {chapters.map((chapter, index) => {
          const selected = chapter.id === selectedChapterId;
          const status = journeyChapterStatusPresentation[chapter.status];
          return (
            <div className="flex items-center gap-4" key={chapter.id}>
              <button
                aria-current={selected ? 'step' : undefined}
                className={cn(
                  'radius-card border-border bg-card min-touch-target focus-visible:ring-ring flex min-h-40 w-72 flex-col gap-4 border p-6 text-left shadow-none focus-visible:ring-2 focus-visible:outline-none',
                  selected && 'border-primary',
                )}
                onClick={() => onSelectChapter(chapter.id)}
                type="button"
              >
                <div className="flex items-start justify-between gap-3">
                  <StatusBadge label={status.label} variant={status.tone} />
                  {chapter.status === 'emerging' ? (
                    <Sparkles
                      aria-hidden="true"
                      className="text-accent size-5"
                    />
                  ) : null}
                </div>
                <div className="space-y-2">
                  <Typography as="span" variant="componentTitle">
                    {chapter.title}
                  </Typography>
                  <Typography
                    as="span"
                    className="text-muted-foreground block"
                    variant="metadata"
                  >
                    {formatLongDate(chapter.start)}–
                    {chapter.end ? formatLongDate(chapter.end) : 'Present'}
                  </Typography>
                </div>
                <div className="flex flex-wrap gap-2">
                  {chapter.themes.slice(0, 2).map((theme) => (
                    <ThemeBadge key={theme.key} theme={theme.key} />
                  ))}
                </div>
              </button>
              {index < chapters.length - 1 ? (
                <ArrowRight
                  aria-hidden="true"
                  className="text-muted-foreground size-5"
                />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

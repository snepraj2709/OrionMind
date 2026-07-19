'use client';

import { ArrowRight, Sparkles } from 'lucide-react';

import { Surface } from '@/components/cards';
import { StatusBadge, ThemeBadge } from '@/components/data-display';
import { Typography } from '@/components/design-system';
import { formatLongDate } from '@/lib/date';

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
          return (
            <div className="flex items-center gap-4" key={chapter.id}>
              <button
                aria-current={selected ? 'step' : undefined}
                className="radius-card min-touch-target focus-visible:ring-ring w-72 text-left focus-visible:ring-2 focus-visible:outline-none"
                onClick={() => onSelectChapter(chapter.id)}
                type="button"
              >
                <Surface
                  className={
                    selected
                      ? 'border-primary min-h-40 w-full gap-4 p-6'
                      : 'min-h-40 w-full gap-4 p-6'
                  }
                >
                  <div className="flex items-start justify-between gap-3">
                    <StatusBadge
                      label={chapter.status}
                      variant={
                        chapter.status === 'current' ? 'success' : 'neutral'
                      }
                    />
                    {chapter.status === 'emerging' ? (
                      <Sparkles
                        aria-hidden="true"
                        className="text-accent size-5"
                      />
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    <Typography as="h3" variant="componentTitle">
                      {chapter.title}
                    </Typography>
                    <Typography
                      className="text-muted-foreground"
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
                </Surface>
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

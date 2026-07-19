'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useState } from 'react';

import { StatusBadge, ThemeBadge } from '@/components/data-display';
import { AppButton, Typography } from '@/components/design-system';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { formatLongDate } from '@/lib/date';
import type { EvidenceItem } from '@/types/evidence';

export interface EvidenceDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: EvidenceItem[];
  title?: string;
}

export function EvidenceDrawer({
  items,
  onOpenChange,
  open,
  title = 'Supporting entries',
}: EvidenceDrawerProps) {
  const [index, setIndex] = useState(0);
  const safeIndex = Math.min(index, Math.max(0, items.length - 1));
  const item = items[safeIndex];

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) setIndex(0);
    onOpenChange(nextOpen);
  }

  return (
    <Sheet onOpenChange={handleOpenChange} open={open}>
      <SheetContent className="bg-card w-full sm:max-w-md" side="right">
        <SheetHeader className="border-border border-b p-6">
          <SheetTitle asChild>
            <Typography as="h2" variant="componentTitle">
              {title}
            </Typography>
          </SheetTitle>
          <SheetDescription>
            Original journal wording is shown separately from Orion&apos;s
            interpretation.
          </SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          {item ? (
            <article className="space-y-6">
              <div className="flex flex-wrap items-center gap-3">
                <StatusBadge label={item.source} variant="neutral" />
                {item.theme ? <ThemeBadge theme={item.theme} /> : null}
                {item.rank ? (
                  <StatusBadge label={`${item.rank} theme`} variant="neutral" />
                ) : null}
                <Typography
                  className="text-muted-foreground"
                  variant="metadata"
                >
                  {formatLongDate(item.date)}
                </Typography>
              </div>
              <div className="space-y-2">
                <Typography variant="eyebrow">Your journal</Typography>
                <Typography as="blockquote" variant="journalExcerpt">
                  {item.text}
                </Typography>
              </div>
              {item.interpretation ? (
                <div className="border-border space-y-2 border-t pt-6">
                  <Typography variant="eyebrow">
                    Orion&apos;s interpretation
                  </Typography>
                  <Typography className="text-muted-foreground" variant="body">
                    {item.interpretation}
                  </Typography>
                </div>
              ) : null}
              {item.supports ? (
                <div className="border-border space-y-2 border-t pt-6">
                  <Typography variant="eyebrow">Supports</Typography>
                  <Typography className="text-muted-foreground" variant="body">
                    {item.supports}
                  </Typography>
                </div>
              ) : null}
            </article>
          ) : (
            <Typography className="text-muted-foreground" variant="body">
              No supporting entries are available for this interpretation.
            </Typography>
          )}
        </div>

        <SheetFooter className="border-border border-t p-4">
          <Typography
            className="text-muted-foreground text-center"
            variant="metadata"
          >
            {items.length > 0
              ? `${safeIndex + 1} of ${items.length}`
              : 'No evidence'}
          </Typography>
          <div className="flex justify-between gap-3">
            <AppButton
              disabled={safeIndex === 0}
              leftIcon={<ChevronLeft aria-hidden="true" />}
              onClick={() => setIndex((current) => Math.max(0, current - 1))}
              size="compact"
              variant="secondary"
            >
              Previous
            </AppButton>
            <AppButton
              disabled={safeIndex >= items.length - 1}
              onClick={() =>
                setIndex((current) => Math.min(items.length - 1, current + 1))
              }
              rightIcon={<ChevronRight aria-hidden="true" />}
              size="compact"
              variant="secondary"
            >
              Next
            </AppButton>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

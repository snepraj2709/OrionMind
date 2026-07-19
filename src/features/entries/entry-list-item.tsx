import { ChevronRight, Mic } from 'lucide-react';

import { StatusBadge, ThemeBadge } from '@/components/data-display';
import { Typography } from '@/components/design-system';
import { AppLink } from '@/components/navigation';
import { entryDetailPath } from '@/config/routes';
import { entryStatusPresentation } from '@/config/status';
import type { EntrySummary } from '@/types/records';

const entryDateFormatter = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
});

interface EntryListItemProps {
  entry: EntrySummary;
}

export function EntryListItem({ entry }: EntryListItemProps) {
  const status = entryStatusPresentation[entry.status];

  return (
    <li className="border-border border-b">
      <AppLink
        className="group radius-card hover:bg-secondary/50 focus-visible:bg-secondary/50 w-full items-start gap-4 px-6 py-4 text-left"
        href={entryDetailPath(entry.id)}
      >
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Typography
              as="span"
              className="text-muted-foreground"
              variant="metadata"
            >
              <time dateTime={entry.date}>
                {entryDateFormatter.format(new Date(entry.date))}
              </time>
            </Typography>

            {entry.inputType === 'voice' ? (
              <span className="text-muted-foreground flex items-center gap-1">
                <Mic aria-hidden="true" className="size-4" />
                <Typography as="span" variant="metadata">
                  Voice
                </Typography>
              </span>
            ) : null}

            {entry.themes.map((theme) => (
              <ThemeBadge key={theme} theme={theme} />
            ))}

            {entry.status !== 'completed' ? (
              <StatusBadge label={status.label} variant={status.tone} />
            ) : null}
          </div>

          <Typography
            className="text-foreground line-clamp-2"
            variant="journalExcerpt"
          >
            {entry.content}
          </Typography>
        </div>

        <ChevronRight
          aria-hidden="true"
          className="text-muted-foreground group-hover:text-foreground mt-1 size-5 shrink-0 transition-colors"
        />
      </AppLink>
    </li>
  );
}

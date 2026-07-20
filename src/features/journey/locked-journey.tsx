import { CalendarDays, FileText, LockKeyhole } from 'lucide-react';

import { Surface } from '@/components/cards';
import { ProgressMetric, StatusBadge } from '@/components/data-display';
import { Typography } from '@/components/design-system';
import { ContentGrid } from '@/components/layout';

import { JOURNEY_UNLOCK_REQUIREMENTS } from './constants';
import type { JourneyStatusResponse, JourneySteamPoint } from './model';
import { JourneySteamgraph } from './journey-steamgraph';

export interface LockedJourneyProps {
  status: JourneyStatusResponse;
  stream: JourneySteamPoint[];
}

export function LockedJourney({ status, stream }: LockedJourneyProps) {
  return (
    <div className="space-y-6">
      <Surface className="sidebar:p-8 gap-0 p-6">
        <div className="sidebar:grid-cols-2 grid gap-8">
          <div className="flex flex-col items-center gap-6 text-center sm:flex-row sm:text-left">
            <span
              aria-hidden="true"
              className="bg-secondary text-muted-foreground radius-pill flex size-20 shrink-0 items-center justify-center"
            >
              <LockKeyhole className="size-10" />
            </span>
            <div className="space-y-3">
              <Typography as="h2" variant="componentTitle">
                Not enough data yet
              </Typography>
              <Typography
                className="text-muted-foreground text-measure"
                variant="body"
              >
                Journey unlocks after 30 days of signup with at least 15 entries
                across those 30 days.
              </Typography>
            </div>
          </div>
          <div className="border-border sidebar:border-t-0 sidebar:border-l sidebar:pt-0 sidebar:pl-8 space-y-6 border-t pt-8">
            <ProgressMetric
              current={status.daysSinceSignup}
              icon={<CalendarDays className="size-6" />}
              label="Days since signup"
              target={JOURNEY_UNLOCK_REQUIREMENTS.daysSinceSignup}
              tone="primary"
            />
            <ProgressMetric
              current={status.entriesAdded}
              icon={<FileText className="size-6" />}
              label="Entries added"
              target={JOURNEY_UNLOCK_REQUIREMENTS.entriesAdded}
              tone="accent"
            />
          </div>
        </div>
      </Surface>

      <ContentGrid columns="two">
        <Surface className="min-state-contained min-w-0 gap-8 p-8">
          <div className="space-y-2">
            <div className="flex flex-wrap items-baseline gap-2">
              <Typography as="h2" variant="componentTitle">
                Your journey
              </Typography>
              <Typography className="text-muted-foreground" variant="bodySmall">
                (locked)
              </Typography>
            </div>
            <Typography className="text-muted-foreground" variant="bodySmall">
              This will be your personal journey once unlocked.
            </Typography>
          </div>
          <JourneySteamgraph
            muted
            points={stream}
            title="Locked preview of your personal journey"
          />
          <div className="border-border flex items-center gap-4 border-t pt-6">
            <span
              aria-hidden="true"
              className="bg-secondary text-muted-foreground radius-pill flex size-12 shrink-0 items-center justify-center"
            >
              <LockKeyhole className="size-6" />
            </span>
            <Typography className="text-muted-foreground" variant="body">
              Add more entries and check back soon.
            </Typography>
          </div>
        </Surface>

        <Surface className="min-state-contained min-w-0 gap-8 p-8">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-2">
              <Typography as="h2" variant="componentTitle">
                Preview of an unlocked journey
              </Typography>
              <Typography className="text-muted-foreground" variant="bodySmall">
                Here’s an example of what your journey could look like.
              </Typography>
            </div>
            <StatusBadge label="Sample" variant="neutral" />
          </div>
          <JourneySteamgraph
            points={stream}
            title="Sample unlocked journey theme streamgraph"
          />
          <Typography className="text-muted-foreground" variant="bodySmall">
            Sample data for illustration only.
          </Typography>
        </Surface>
      </ContentGrid>
    </div>
  );
}

import { Scale } from 'lucide-react';

import { Surface } from '@/components/cards';
import { AppButton, Typography } from '@/components/design-system';

import type { InnerTension } from './model';

const dateFormatter = new Intl.DateTimeFormat('en', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
});

export interface InnerTensionCardProps {
  tension: InnerTension;
  response?: 'resonates' | 'rejected';
  onResponseChange: (response: 'resonates' | 'rejected') => void;
  onViewEvidence: () => void;
}

export function InnerTensionCard({
  onResponseChange,
  onViewEvidence,
  response,
  tension,
}: InnerTensionCardProps) {
  return (
    <Surface className={response === 'rejected' ? 'bg-muted p-6' : 'p-6'}>
      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <Typography as="h3" variant="componentTitle">
            {tension.leftTitle}
          </Typography>
          <Typography className="text-muted-foreground" variant="body">
            {tension.leftBody}
          </Typography>
        </div>
        <div className="space-y-2 md:text-right">
          <Typography as="h3" variant="componentTitle">
            {tension.rightTitle}
          </Typography>
          <Typography className="text-muted-foreground" variant="body">
            {tension.rightBody}
          </Typography>
        </div>
      </div>

      <div
        className="flex items-center gap-3 py-2"
        aria-label="Both needs are valid"
      >
        <span aria-hidden="true" className="bg-accent radius-pill size-3" />
        <span className="bg-border h-px flex-1" />
        <Scale aria-hidden="true" className="text-muted-foreground size-5" />
        <span className="bg-border h-px flex-1" />
        <span aria-hidden="true" className="bg-primary radius-pill size-3" />
      </div>

      <div className="bg-secondary radius-control space-y-2 p-4">
        <Typography variant="eyebrow">A possible integration</Typography>
        <Typography variant="body">{tension.integration}</Typography>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <Typography className="text-muted-foreground" variant="metadata">
          Appeared together:{' '}
          {tension.dates
            .map((date) => dateFormatter.format(new Date(date)))
            .join(', ')}
        </Typography>
        <div className="flex flex-wrap gap-2">
          <AppButton onClick={onViewEvidence} size="compact" variant="link">
            View evidence
          </AppButton>
          <AppButton onClick={onViewEvidence} size="compact" variant="link">
            Why am I seeing this?
          </AppButton>
          <AppButton
            aria-pressed={response === 'resonates'}
            onClick={() => onResponseChange('resonates')}
            size="compact"
            variant={response === 'resonates' ? 'secondary' : 'ghost'}
          >
            Resonates
          </AppButton>
          <AppButton
            aria-pressed={response === 'rejected'}
            onClick={() => onResponseChange('rejected')}
            size="compact"
            variant={response === 'rejected' ? 'secondary' : 'ghost'}
          >
            Does not resonate
          </AppButton>
        </div>
      </div>
      {response ? (
        <Typography
          aria-live="polite"
          className="text-muted-foreground"
          variant="bodySmall"
        >
          {response === 'rejected'
            ? 'Marked as not resonating. Orion will not treat this tension as an accepted self-pattern.'
            : 'Marked as resonating with your experience.'}
        </Typography>
      ) : null}
    </Surface>
  );
}

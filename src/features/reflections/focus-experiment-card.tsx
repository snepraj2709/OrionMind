import { Target } from 'lucide-react';

import { Surface } from '@/components/cards';
import { AppButton, Typography } from '@/components/design-system';

import type { ReflectionViewModel } from './model';

export interface FocusExperimentCardProps {
  focus: ReflectionViewModel['focus'];
  response?: string;
  onResponseChange: (response: string) => void;
  onViewEvidence: () => void;
}

export function FocusExperimentCard({
  focus,
  onResponseChange,
  onViewEvidence,
  response,
}: FocusExperimentCardProps) {
  if (response === 'dismissed') return null;

  return (
    <Surface className="border-accent bg-muted gap-6 p-6 sm:p-8">
      <div className="flex items-center gap-3">
        <Target aria-hidden="true" className="text-accent size-5" />
        <Typography variant="eyebrow">What deserves your focus now</Typography>
      </div>
      <div className="text-measure space-y-4">
        <Typography as="h2" variant="sectionTitle">
          {focus.title}
        </Typography>
        <Typography variant="reflectiveStatement">{focus.body}</Typography>
        <div className="border-border space-y-2 border-t pt-6">
          <Typography variant="eyebrow">Suggested experiment</Typography>
          <Typography variant="body">{focus.experiment}</Typography>
        </div>
        <AppButton onClick={onViewEvidence} size="compact" variant="link">
          Why am I seeing this?
        </AppButton>
      </div>
      <div className="flex flex-wrap gap-3">
        <AppButton
          aria-pressed={response === 'trying'}
          onClick={() => onResponseChange('trying')}
        >
          Try this for 7 days
        </AppButton>
        <AppButton
          aria-pressed={response === 'another'}
          onClick={() => onResponseChange('another')}
          variant="secondary"
        >
          Choose another focus
        </AppButton>
        <AppButton
          onClick={() => onResponseChange('dismissed')}
          variant="ghost"
        >
          Dismiss
        </AppButton>
      </div>
      {response === 'trying' ? (
        <Typography
          aria-live="polite"
          className="text-muted-foreground"
          variant="bodySmall"
        >
          Saved as a seven-day experiment. This is an invitation, not a
          requirement.
        </Typography>
      ) : null}
    </Surface>
  );
}

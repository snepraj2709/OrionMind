import { RotateCw } from 'lucide-react';

import { Surface } from '@/components/cards';
import { AppButton, Typography } from '@/components/design-system';
import { ContentGrid } from '@/components/layout';

import type { ReflectionViewModel } from './model';

export interface RecurringLoopProps {
  loop: ReflectionViewModel['loop'];
  feedback?: string;
  onFeedbackChange: (value: string) => void;
  onViewEvidence: (stepIndex?: number) => void;
}

export function RecurringLoop({
  feedback,
  loop,
  onFeedbackChange,
  onViewEvidence,
}: RecurringLoopProps) {
  return (
    <ContentGrid columns="editorial">
      <Surface className="p-6 sm:p-8">
        <ol className="border-border space-y-0 border-l">
          {loop.steps.map((step, index) => (
            <li className="relative pb-6 pl-6 last:pb-0" key={step.id}>
              <span
                aria-hidden="true"
                className="bg-card border-accent radius-pill absolute top-1 -left-2 flex size-4 items-center justify-center border"
              />
              <Typography variant="body">{step.text}</Typography>
              <AppButton
                onClick={() => onViewEvidence(index)}
                size="compact"
                variant="link"
              >
                View evidence
              </AppButton>
            </li>
          ))}
        </ol>
        <div className="border-border mt-6 flex items-center gap-3 border-t pt-6">
          <RotateCw aria-hidden="true" className="text-accent size-5" />
          <Typography className="text-muted-foreground" variant="bodySmall">
            The final step appears to reopen the first, allowing the pattern to
            repeat.
          </Typography>
        </div>
      </Surface>

      <div className="space-y-4">
        <Surface className="bg-muted space-y-6 p-6">
          <div className="space-y-2">
            <Typography as="h3" variant="componentTitle">
              What this loop may be protecting
            </Typography>
            <Typography variant="body">{loop.protection}</Typography>
          </div>
          <div className="border-border space-y-2 border-t pt-6">
            <Typography as="h3" variant="componentTitle">
              A possible way to interrupt it
            </Typography>
            <Typography variant="body">{loop.interruption}</Typography>
          </div>
          <AppButton
            onClick={() => onViewEvidence()}
            size="compact"
            variant="link"
          >
            Why am I seeing this?
          </AppButton>
        </Surface>
        <div
          className="flex flex-wrap gap-2"
          role="group"
          aria-label="Loop feedback"
        >
          {[
            ['often', 'This happens often'],
            ['sometimes', 'Sometimes'],
            ['unrecognized', "I don't recognize this"],
            ['saved', 'Save as something to notice'],
          ].map(([value, label]) => (
            <AppButton
              aria-pressed={feedback === value}
              key={value}
              onClick={() => onFeedbackChange(value!)}
              size="compact"
              variant={feedback === value ? 'secondary' : 'ghost'}
            >
              {label}
            </AppButton>
          ))}
        </div>
      </div>
    </ContentGrid>
  );
}

import { Shield, Zap } from 'lucide-react';

import { Typography } from '@/components/design-system';
import { ContentGrid } from '@/components/layout';

import { LoopOverviewDiagram } from './loop-overview-diagram';
import type { AvailableRecurringLoop, ReflectionResponse } from './model';
import { ReflectionFeedbackSurface } from './reflection-feedback-surface';
import { ReflectionResponseBar } from './reflection-response-bar';

export interface RecurringLoopProps {
  loop: AvailableRecurringLoop;
  response: ReflectionResponse | null;
  onResponseChange: (value: ReflectionResponse) => void;
  onViewEvidence: () => void;
  pending?: boolean;
  error?: string;
}

export function RecurringLoop({
  error,
  loop,
  onResponseChange,
  onViewEvidence,
  pending = false,
  response,
}: RecurringLoopProps) {
  return (
    <ReflectionFeedbackSurface
      className="overflow-hidden p-0"
      pending={pending}
      response={response}
    >
      <ContentGrid columns="reflectionTriptych">
        <div className="p-6">
          <LoopOverviewDiagram />
        </div>
        <div className="p-6">
          <Typography as="h3" className="mb-4" variant="body">
            How this loop unfolds
          </Typography>
          <ol>
            {loop.steps.map((step, index) => (
              <li key={step.id}>
                <div className="flex gap-3 p-3">
                  <span className="type-metadata radius-pill border-border flex size-8 shrink-0 items-center justify-center border">
                    {index + 1}
                  </span>
                  <span className="min-w-0">
                    <Typography variant="bodySmall">{step.text}</Typography>
                  </span>
                </div>
                {index < loop.steps.length - 1 ? (
                  <hr className="border-border" />
                ) : null}
              </li>
            ))}
          </ol>
        </div>
        <div className="flex flex-col">
          <div className="flex-1 space-y-4 p-6">
            <span className="bg-primary/10 radius-pill text-primary flex size-12 items-center justify-center">
              <Shield aria-hidden="true" className="size-5" />
            </span>
            <Typography variant="eyebrow">
              What this loop may be protecting
            </Typography>
            <Typography variant="journalExcerpt">{loop.protection}</Typography>
          </div>
          <div className="border-border flex-1 space-y-4 border-t p-6">
            <span className="bg-primary/10 radius-pill text-primary flex size-12 items-center justify-center">
              <Zap aria-hidden="true" className="size-5" />
            </span>
            <Typography variant="eyebrow">
              A possible way to interrupt it
            </Typography>
            <Typography variant="journalExcerpt">
              {loop.interruption}
            </Typography>
          </div>
        </div>
      </ContentGrid>
      <ReflectionResponseBar
        ariaLabel="Recurring loop feedback"
        className="border-border border-t p-6"
        error={error}
        onResponseChange={onResponseChange}
        onViewEvidence={onViewEvidence}
        pending={pending}
        response={response}
      />
    </ReflectionFeedbackSurface>
  );
}

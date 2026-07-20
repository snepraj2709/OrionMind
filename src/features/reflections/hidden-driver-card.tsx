import { BarChart3 } from 'lucide-react';

import { Typography } from '@/components/design-system';
import { ContentGrid } from '@/components/layout';

import type { ReflectionResponse, ReflectionViewModel } from './model';
import { ReflectionFeedbackSurface } from './reflection-feedback-surface';
import { ReflectionResponseBar } from './reflection-response-bar';

export interface HiddenDriverCardProps {
  driver: ReflectionViewModel['hiddenDriver'];
  response?: ReflectionResponse;
  onResponseChange: (value: ReflectionResponse) => void;
  onViewEvidence: () => void;
}

export function HiddenDriverCard({
  driver,
  onResponseChange,
  onViewEvidence,
  response,
}: HiddenDriverCardProps) {
  return (
    <ReflectionFeedbackSurface className="sidebar:p-8 p-6" response={response}>
      <ContentGrid columns="reflectionSplit">
        <div className="sidebar:pr-8 space-y-6">
          <Typography as="h2" variant="reflectiveStatement">
            {driver.statement}
          </Typography>
          <Typography className="text-muted-foreground" variant="bodyLarge">
            {driver.underlyingNeed}
          </Typography>
          <div className="flex flex-wrap gap-2" aria-label="Hidden drivers">
            {driver.drivers.map((item) => (
              <span
                className="type-metadata radius-pill border-border bg-background text-foreground border px-3 py-2"
                key={item}
              >
                {item}
              </span>
            ))}
          </div>
        </div>
        <div className="space-y-6">
          <Typography variant="eyebrow">
            Evidence from your reflections
          </Typography>
          <ul className="divide-border divide-y">
            {driver.evidenceStrength.map((item) => (
              <li className="type-body flex gap-3 py-4 first:pt-0" key={item}>
                <span aria-hidden="true">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-3">
            <BarChart3
              aria-hidden="true"
              className="text-selection-strong size-6"
            />
            <Typography variant="body">Observed across 8 entries</Typography>
          </div>
        </div>
      </ContentGrid>
      <ReflectionResponseBar
        ariaLabel="Hidden driver feedback"
        className="border-border mt-8 border-t pt-6"
        onResponseChange={onResponseChange}
        onViewEvidence={onViewEvidence}
        response={response}
      />
    </ReflectionFeedbackSurface>
  );
}

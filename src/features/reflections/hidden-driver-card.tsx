import { BarChart3 } from 'lucide-react';

import { Typography } from '@/components/design-system';
import { ContentGrid } from '@/components/layout';

import type { AvailableHiddenDriver, ReflectionResponse } from './model';
import { ReflectionFeedbackSurface } from './reflection-feedback-surface';
import { ReflectionResponseBar } from './reflection-response-bar';

export interface HiddenDriverCardProps {
  driver: AvailableHiddenDriver;
  response: ReflectionResponse | null;
  onResponseChange: (value: ReflectionResponse) => void;
  onViewEvidence: () => void;
  pending?: boolean;
  error?: string;
}

export function HiddenDriverCard({
  driver,
  error,
  onResponseChange,
  onViewEvidence,
  pending = false,
  response,
}: HiddenDriverCardProps) {
  const supportingEntryCount = new Set(
    driver.evidence.map((item) => item.entryDate),
  ).size;

  return (
    <ReflectionFeedbackSurface
      className="sidebar:p-8 p-6"
      pending={pending}
      response={response}
    >
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
            Signals across your reflections
          </Typography>
          <ul className="divide-border divide-y">
            {driver.evidence.slice(0, 3).map((item) => (
              <li
                className="type-body flex gap-3 py-4 first:pt-0"
                key={item.id}
              >
                <span aria-hidden="true">•</span>
                <span>{item.interpretation}</span>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-3">
            <BarChart3
              aria-hidden="true"
              className="text-selection-strong size-6"
            />
            <Typography variant="body">
              Supported by {supportingEntryCount}{' '}
              {supportingEntryCount === 1 ? 'entry' : 'entries'}
            </Typography>
          </div>
        </div>
      </ContentGrid>
      <ReflectionResponseBar
        ariaLabel="Hidden driver feedback"
        className="border-border mt-8 border-t pt-6"
        error={error}
        onResponseChange={onResponseChange}
        onViewEvidence={onViewEvidence}
        pending={pending}
        response={response}
      />
    </ReflectionFeedbackSurface>
  );
}

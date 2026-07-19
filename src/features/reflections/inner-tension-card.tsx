import { Sparkles } from 'lucide-react';

import { Surface } from '@/components/cards';
import { Typography } from '@/components/design-system';

import type { InnerTension, ReflectionResponse } from './model';
import { ReflectionResponseBar } from './reflection-response-bar';

export interface InnerTensionCardProps {
  tension: InnerTension;
  response?: ReflectionResponse;
  onResponseChange: (response: ReflectionResponse) => void;
  onViewEvidence: () => void;
}

function TensionConnector() {
  return (
    <div
      aria-label="Two needs held in tension"
      className="flex items-center justify-center"
    >
      <div className="sidebar:h-auto relative flex h-16 w-full items-center justify-center">
        <span className="bg-primary sidebar:top-auto sidebar:left-0 sidebar:h-px sidebar:w-1/2 absolute top-0 h-8 w-px" />
        <span className="bg-counterpoint sidebar:right-0 sidebar:bottom-auto sidebar:h-px sidebar:w-1/2 absolute bottom-0 h-8 w-px" />
        <span className="bg-card border-selection-strong radius-pill z-10 size-4 border" />
      </div>
    </div>
  );
}

export function InnerTensionCard({
  onResponseChange,
  onViewEvidence,
  response,
  tension,
}: InnerTensionCardProps) {
  return (
    <Surface className={response === 'rejected' ? 'bg-muted p-6' : 'p-6'}>
      <div className="sidebar:grid-cols-[minmax(0,1fr)_minmax(12rem,0.8fr)_minmax(0,1fr)] grid grid-cols-1 gap-6">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="bg-primary radius-pill size-3"
            />
            <Typography
              as="h3"
              className="text-primary"
              variant="componentTitle"
            >
              {tension.leftTitle}
            </Typography>
          </div>
          <Typography variant="body">{tension.leftBody}</Typography>
        </div>
        <TensionConnector />
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="bg-counterpoint radius-pill size-3"
            />
            <Typography
              as="h3"
              className="text-counterpoint"
              variant="componentTitle"
            >
              {tension.rightTitle}
            </Typography>
          </div>
          <Typography variant="body">{tension.rightBody}</Typography>
        </div>
      </div>

      <div className="border-border flex gap-4 border-t pt-6">
        <Sparkles
          aria-hidden="true"
          className="text-selection-strong mt-1 size-5 shrink-0"
        />
        <div className="space-y-2">
          <Typography variant="eyebrow">Possible integration</Typography>
          <Typography variant="journalExcerpt">
            {tension.integration}
          </Typography>
        </div>
      </div>

      <ReflectionResponseBar
        ariaLabel={`${tension.leftTitle} and ${tension.rightTitle} feedback`}
        className="border-border border-t pt-6"
        onResponseChange={onResponseChange}
        onViewEvidence={onViewEvidence}
        response={response}
      />
    </Surface>
  );
}

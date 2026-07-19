import type { ReactNode } from 'react';

import { Surface } from '@/components/cards';
import { Typography } from '@/components/design-system';

export interface ReviewItemCardProps {
  title: string;
  content: string;
  status: ReactNode;
  actions?: ReactNode;
  metadata?: ReactNode;
}

export function ReviewItemCard({
  actions,
  content,
  metadata,
  status,
  title,
}: ReviewItemCardProps) {
  return (
    <Surface className="gap-4 p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <Typography as="h3" variant="componentTitle">
            {title}
          </Typography>
          {metadata ? (
            <div className="type-body-small text-muted-foreground">
              {metadata}
            </div>
          ) : null}
        </div>
        <div className="shrink-0">{status}</div>
      </div>
      <Typography className="text-measure" variant="journalExcerpt">
        {content}
      </Typography>
      {actions ? <div className="pt-2">{actions}</div> : null}
    </Surface>
  );
}

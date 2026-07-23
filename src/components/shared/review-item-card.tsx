import type { ReactNode } from 'react';

import { Surface } from '@/components/cards';
import { Typography } from '@/components/design-system';

export interface ReviewItemCardProps {
  title?: string;
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
  const hasHeadingContent = Boolean(title || metadata);

  return (
    <Surface className="gap-4 p-6">
      {hasHeadingContent ? (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 space-y-1">
              {title ? (
                <Typography as="h3" variant="componentTitle">
                  {title}
                </Typography>
              ) : null}
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
        </>
      ) : (
        <div className="min-w-0">
          <div className="float-right mb-2 ml-4">{status}</div>
          <Typography className="text-measure" variant="journalExcerpt">
            {content}
          </Typography>
        </div>
      )}
      {actions ? <div className="pt-2">{actions}</div> : null}
    </Surface>
  );
}

import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';

import { ContentCard, type ContentCardProps } from './content-card';

export interface EntryCardProps extends Omit<ContentCardProps, 'children'> {
  excerpt: ReactNode;
  metadata?: ReactNode;
  status?: ReactNode;
}

export function EntryCard({
  excerpt,
  metadata,
  status,
  ...props
}: EntryCardProps) {
  return (
    <ContentCard actions={status} variant="interactive" {...props}>
      <div className="space-y-4">
        <Typography className="text-measure-wide" variant="journalExcerpt">
          {excerpt}
        </Typography>
        {metadata ? (
          <div className="type-metadata text-muted-foreground">{metadata}</div>
        ) : null}
      </div>
    </ContentCard>
  );
}

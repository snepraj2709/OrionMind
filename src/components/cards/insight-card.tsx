import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';

import { ContentCard, type ContentCardProps } from './content-card';

export interface InsightCardProps extends Omit<ContentCardProps, 'children'> {
  insight: ReactNode;
  evidence?: ReactNode;
}

export function InsightCard({ evidence, insight, ...props }: InsightCardProps) {
  return (
    <ContentCard {...props}>
      <div className="space-y-4">
        <Typography variant="bodyLarge">{insight}</Typography>
        {evidence ? (
          <div className="border-border border-t pt-4">
            <Typography className="text-muted-foreground" variant="bodySmall">
              {evidence}
            </Typography>
          </div>
        ) : null}
      </div>
    </ContentCard>
  );
}

import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';

import { ContentCard, type ContentCardProps } from './content-card';

export interface StatCardProps extends Omit<ContentCardProps, 'children'> {
  value: ReactNode;
  label: string;
  context?: ReactNode;
}

export function StatCard({ context, label, value, ...props }: StatCardProps) {
  return (
    <ContentCard {...props}>
      <div className="space-y-2">
        <Typography as="p" variant="display">
          {value}
        </Typography>
        <Typography variant="metadata">{label}</Typography>
        {context ? (
          <Typography className="text-muted-foreground" variant="bodySmall">
            {context}
          </Typography>
        ) : null}
      </div>
    </ContentCard>
  );
}

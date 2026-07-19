import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';

import { ContentCard, type ContentCardProps } from './content-card';

export interface ReflectionCardProps extends Omit<
  ContentCardProps,
  'children'
> {
  statement: ReactNode;
  supportingText?: ReactNode;
}

export function ReflectionCard({
  statement,
  supportingText,
  ...props
}: ReflectionCardProps) {
  return (
    <ContentCard className="border-l-accent border-l-4" {...props}>
      <div className="space-y-4">
        <Typography as="blockquote" variant="reflectiveStatement">
          {statement}
        </Typography>
        {supportingText ? (
          <Typography className="text-muted-foreground" variant="body">
            {supportingText}
          </Typography>
        ) : null}
      </div>
    </ContentCard>
  );
}

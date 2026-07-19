import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';
import { cn } from '@/lib/utils';

export interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  eyebrow?: string;
  actions?: ReactNode;
  breadcrumbs?: ReactNode;
  className?: string;
}

export function PageHeader({
  actions,
  breadcrumbs,
  className,
  description,
  eyebrow,
  title,
}: PageHeaderProps) {
  return (
    <header className={cn('space-y-4', className)}>
      {breadcrumbs}
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="text-measure space-y-2">
          {eyebrow ? (
            <Typography className="text-muted-foreground" variant="eyebrow">
              {eyebrow}
            </Typography>
          ) : null}
          <Typography as="h1" variant="pageTitle">
            {title}
          </Typography>
          {description ? (
            <Typography className="text-muted-foreground" variant="bodyLarge">
              {description}
            </Typography>
          ) : null}
        </div>
        {actions ? (
          <div className="flex flex-wrap items-center gap-3">{actions}</div>
        ) : null}
      </div>
    </header>
  );
}

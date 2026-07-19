import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';
import { cn } from '@/lib/utils';

export interface SectionProps {
  children: ReactNode;
  title?: string;
  description?: string;
  actions?: ReactNode;
  headingId?: string;
  className?: string;
}

export function Section({
  actions,
  children,
  className,
  description,
  headingId,
  title,
}: SectionProps) {
  return (
    <section
      aria-labelledby={title && headingId ? headingId : undefined}
      className={cn('space-y-6', className)}
    >
      {title ? (
        <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="text-measure space-y-2">
            <Typography as="h2" id={headingId} variant="sectionTitle">
              {title}
            </Typography>
            {description ? (
              <Typography className="text-muted-foreground" variant="body">
                {description}
              </Typography>
            ) : null}
          </div>
          {actions ? <div>{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

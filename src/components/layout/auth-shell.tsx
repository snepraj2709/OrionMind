import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';
import { cn } from '@/lib/utils';

import { PublicShell } from './public-shell';

export interface AuthShellProps {
  children: ReactNode;
  title: string;
  description?: string;
  brand?: ReactNode;
  footer?: ReactNode;
  className?: string;
  contained?: boolean;
}

export function AuthShell({
  brand,
  children,
  className,
  contained,
  description,
  footer,
  title,
}: AuthShellProps) {
  return (
    <PublicShell contained={contained}>
      <div className={cn('w-full max-w-md space-y-8', className)}>
        {brand ? <div>{brand}</div> : null}
        <header className="space-y-2">
          <Typography as="h1" variant="pageTitle">
            {title}
          </Typography>
          {description ? (
            <Typography className="text-muted-foreground" variant="body">
              {description}
            </Typography>
          ) : null}
        </header>
        {children}
        {footer ? <footer>{footer}</footer> : null}
      </div>
    </PublicShell>
  );
}

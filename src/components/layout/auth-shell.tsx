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
  variant?: 'default' | 'prominent';
}

export function AuthShell({
  brand,
  children,
  className,
  contained,
  description,
  footer,
  title,
  variant = 'default',
}: AuthShellProps) {
  const isProminent = variant === 'prominent';

  return (
    <PublicShell contained={contained}>
      <div
        className={cn(
          'w-full',
          isProminent ? 'lg:w-1/2' : 'max-w-md',
          className,
        )}
      >
        <div className={cn('space-y-8', isProminent && 'lg:space-y-16')}>
          {brand ? <div>{brand}</div> : null}
          <div className={cn('space-y-6', isProminent && 'lg:space-y-8')}>
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
            {footer ? (
              <footer
                className={cn(isProminent && 'flex justify-center text-center')}
              >
                {footer}
              </footer>
            ) : null}
          </div>
        </div>
      </div>
    </PublicShell>
  );
}

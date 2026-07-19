import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

import { PageShell } from './page-shell';

export interface PublicShellProps {
  children: ReactNode;
  className?: string;
  contained?: boolean;
}

export function PublicShell({
  children,
  className,
  contained = false,
}: PublicShellProps) {
  return (
    <PageShell
      as={contained ? 'div' : 'main'}
      className={cn(
        'bg-background flex items-center justify-center',
        contained ? 'min-state-contained' : 'min-h-screen',
        className,
      )}
      id={contained ? undefined : 'main-content'}
    >
      {children}
    </PageShell>
  );
}

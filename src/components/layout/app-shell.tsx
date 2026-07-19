import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export interface AppShellProps {
  children: ReactNode;
  sidebar: ReactNode;
  mobileNavigation: ReactNode;
  className?: string;
}

export function AppShell({
  children,
  className,
  mobileNavigation,
  sidebar,
}: AppShellProps) {
  return (
    <div
      className={cn('bg-background text-foreground min-h-screen', className)}
    >
      <a
        className="type-button bg-primary text-primary-foreground focus:radius-interactive sr-only z-50 px-4 py-3 focus:not-sr-only focus:fixed focus:top-4 focus:left-4"
        href="#main-content"
      >
        Skip to content
      </a>
      <div className="sidebar:hidden">{mobileNavigation}</div>
      <div className="flex min-h-screen">
        {sidebar}
        <main className="min-w-0 flex-1" id="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}

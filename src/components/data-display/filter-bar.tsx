import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export interface FilterBarProps {
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
  ariaLabel?: string;
}

export function FilterBar({
  actions,
  ariaLabel = 'Table filters',
  children,
  className,
}: FilterBarProps) {
  return (
    <div
      aria-label={ariaLabel}
      className={cn(
        'border-border flex flex-col gap-4 border-b pb-4 md:flex-row md:items-end md:justify-between',
        className,
      )}
      role="search"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        {children}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

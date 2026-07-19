import Link from 'next/link';
import type { ComponentProps, ReactNode } from 'react';

import { cn } from '@/lib/utils';

export interface AppLinkProps extends ComponentProps<typeof Link> {
  children: ReactNode;
  isActive?: boolean;
}

export function AppLink({
  children,
  className,
  isActive = false,
  ...props
}: AppLinkProps) {
  return (
    <Link
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'radius-control focus-visible:ring-ring min-touch-target inline-flex items-center transition-colors focus-visible:ring-2 focus-visible:outline-none',
        isActive ? 'text-primary' : 'text-foreground hover:text-primary',
        className,
      )}
      {...props}
    >
      {children}
    </Link>
  );
}

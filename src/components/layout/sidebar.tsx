import type { ReactNode } from 'react';

import { responsiveLayoutVariants } from '@/config/design-system';
import { cn } from '@/lib/utils';

export interface SidebarProps {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  ariaLabel?: string;
  className?: string;
}

export function Sidebar({
  ariaLabel = 'Primary navigation',
  children,
  className,
  footer,
  header,
}: SidebarProps) {
  return (
    <aside
      aria-label={`${ariaLabel} sidebar`}
      className={cn(
        responsiveLayoutVariants.desktopSidebar,
        'border-border bg-sidebar sticky top-0 h-screen flex-col border-r',
        className,
      )}
    >
      {header ? <div className="p-6">{header}</div> : null}
      <nav
        aria-label={ariaLabel}
        className="min-h-0 flex-1 overflow-y-auto p-3"
      >
        {children}
      </nav>
      {footer ? (
        <footer className="border-border border-t p-4">{footer}</footer>
      ) : null}
    </aside>
  );
}

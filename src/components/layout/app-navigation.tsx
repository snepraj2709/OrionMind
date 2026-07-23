'use client';

import { usePathname } from 'next/navigation';

import { NavItem } from '@/components/navigation';
import { getActiveSidebarRoute, sidebarRoutes } from '@/config/routes';
import { cn } from '@/lib/utils';

export interface AppNavigationProps {
  className?: string;
  reviewCount?: number;
}

export function AppNavigation({
  className,
  reviewCount = 0,
}: AppNavigationProps) {
  const pathname = usePathname();
  const activeRoute = getActiveSidebarRoute(pathname);

  return (
    <div className={cn('space-y-1', className)}>
      {sidebarRoutes.map(({ icon: Icon, key, label, path }) => (
        <NavItem
          badge={
            key === 'review' && reviewCount > 0 ? (
              <span
                aria-label={`${reviewCount} items to review`}
                className="type-metadata radius-pill bg-status-warning/10 text-foreground px-2 py-1"
              >
                {reviewCount}
              </span>
            ) : undefined
          }
          href={path}
          icon={<Icon className="size-4" />}
          isActive={key === activeRoute}
          key={key}
          label={label}
        />
      ))}
    </div>
  );
}

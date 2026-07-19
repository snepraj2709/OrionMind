'use client';

import { usePathname } from 'next/navigation';

import { NavItem } from '@/components/navigation';
import { getActiveSidebarRoute, sidebarRoutes } from '@/config/routes';
import { cn } from '@/lib/utils';

export interface AppNavigationProps {
  className?: string;
}

export function AppNavigation({ className }: AppNavigationProps) {
  const pathname = usePathname();
  const activeRoute = getActiveSidebarRoute(pathname);

  return (
    <div className={cn('space-y-1', className)}>
      {sidebarRoutes.map(({ icon: Icon, key, label, path }) => (
        <NavItem
          href={path}
          icon={<Icon className="icon-md" />}
          isActive={key === activeRoute}
          key={key}
          label={label}
        />
      ))}
    </div>
  );
}

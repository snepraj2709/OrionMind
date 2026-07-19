import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';
import { cn } from '@/lib/utils';

import { AppLink, type AppLinkProps } from './app-link';

export interface NavItemProps extends Omit<AppLinkProps, 'children'> {
  label: string;
  icon?: ReactNode;
  badge?: ReactNode;
}

export function NavItem({
  badge,
  className,
  icon,
  isActive,
  label,
  ...props
}: NavItemProps) {
  return (
    <AppLink
      className={cn(
        'w-full gap-3 px-3 py-2',
        isActive ? 'bg-secondary' : 'hover:bg-muted',
        className,
      )}
      isActive={isActive}
      {...props}
    >
      {icon ? <span aria-hidden="true">{icon}</span> : null}
      <Typography as="span" className="flex-1" variant="navigation">
        {label}
      </Typography>
      {badge}
    </AppLink>
  );
}

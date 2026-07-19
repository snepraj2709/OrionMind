'use client';

import { Typography } from '@/components/design-system';

import { SignOutButton } from './sign-out-button';
import { useAuth } from './use-auth';

export interface UserMenuProps {
  name: string;
}

export function UserMenu({ name }: UserMenuProps) {
  const { user } = useAuth();
  const displayName = user?.name ?? name;
  const initials = displayName
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="radius-control hover:bg-secondary flex items-center gap-2 p-2 transition-colors">
      <div className="bg-secondary radius-pill flex size-8 shrink-0 items-center justify-center">
        <Typography as="span" variant="metadata">
          {initials}
        </Typography>
      </div>
      <div className="min-w-0 flex-1">
        <Typography className="truncate" variant="bodySmall">
          {displayName}
        </Typography>
      </div>
      <SignOutButton iconOnly />
    </div>
  );
}

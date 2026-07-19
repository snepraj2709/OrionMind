'use client';

import { LogOut } from 'lucide-react';
import { useState } from 'react';

import { AppButton } from '@/components/design-system';
import { InlineError } from '@/components/feedback';
import { cn } from '@/lib/utils';

import { useAuth } from './use-auth';

export interface SignOutButtonProps {
  className?: string;
  iconOnly?: boolean;
}

export function SignOutButton({
  className,
  iconOnly = false,
}: SignOutButtonProps) {
  const { isPending, signOut } = useAuth();
  const [error, setError] = useState<string>();

  async function handleSignOut() {
    setError(undefined);
    try {
      await signOut();
    } catch {
      setError('Orion could not log you out. Try again.');
    }
  }

  return (
    <div className={cn('space-y-2', className)}>
      <AppButton
        aria-label={iconOnly ? 'Log out' : undefined}
        className={iconOnly ? undefined : 'w-full justify-start'}
        leftIcon={
          iconOnly ? undefined : (
            <LogOut aria-hidden="true" className="icon-md" />
          )
        }
        loading={isPending}
        loadingLabel="Logging out"
        onClick={() => void handleSignOut()}
        variant={iconOnly ? 'icon' : 'ghost'}
      >
        {iconOnly ? (
          <LogOut aria-hidden="true" className="icon-md" />
        ) : (
          'Log out'
        )}
      </AppButton>
      {error ? <InlineError>{error}</InlineError> : null}
    </div>
  );
}

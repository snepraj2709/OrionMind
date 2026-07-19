'use client';

import { LogOut } from 'lucide-react';
import { useState } from 'react';

import { AppButton } from '@/components/design-system';
import { InlineError } from '@/components/feedback';

import { useAuth } from './use-auth';

export function SignOutButton() {
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
    <div className="space-y-2">
      <AppButton
        className="w-full justify-start"
        leftIcon={<LogOut aria-hidden="true" className="icon-md" />}
        loading={isPending}
        loadingLabel="Logging out"
        onClick={() => void handleSignOut()}
        variant="ghost"
      >
        Log out
      </AppButton>
      {error ? <InlineError>{error}</InlineError> : null}
    </div>
  );
}

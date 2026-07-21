'use client';

import { useRouter } from 'next/navigation';
import type { Route } from 'next';
import { type ReactNode, useEffect } from 'react';

import { PageLoader } from '@/components/feedback';
import { resolvePostAuthPath } from '@/config/routes';

import { AuthConfigurationNotice } from './auth-configuration-notice';
import { useAuth } from './use-auth';

export interface AuthRouteGuardProps {
  children: ReactNode;
}

export function AuthRouteGuard({ children }: AuthRouteGuardProps) {
  const router = useRouter();
  const { flow, isRequiredRecoveryActive, status } = useAuth();
  const isPinnedAuthFlow =
    isRequiredRecoveryActive ||
    flow === 'confirmation_token_validation' ||
    flow === 'confirmation_success' ||
    flow === 'recovery_complete';

  useEffect(() => {
    if (status === 'authenticated' && !isPinnedAuthFlow) {
      const returnTo = new URLSearchParams(window.location.search).get(
        'returnTo',
      );
      router.replace(resolvePostAuthPath(returnTo) as Route);
    }
  }, [isPinnedAuthFlow, router, status]);

  if (status === 'unconfigured') return <AuthConfigurationNotice />;

  if (
    status === 'resolving' ||
    (status === 'authenticated' && !isPinnedAuthFlow)
  ) {
    return <PageLoader label="Restoring your session" />;
  }

  return children;
}

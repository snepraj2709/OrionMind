'use client';

import { useRouter } from 'next/navigation';
import type { Route } from 'next';
import { type ReactNode, useEffect } from 'react';

import { PageLoader } from '@/components/feedback';
import { createLoginRedirect } from '@/config/routes';

import { useAuth } from './use-auth';

export interface ProtectedRouteProps {
  children: ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === 'anonymous' || status === 'unconfigured') {
      const destination = createLoginRedirect(
        window.location.pathname,
        window.location.search,
      );
      router.replace(destination as Route);
    }
  }, [router, status]);

  if (status !== 'authenticated') {
    return <PageLoader label="Restoring your session" />;
  }

  return children;
}

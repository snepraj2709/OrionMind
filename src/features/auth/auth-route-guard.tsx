'use client';

import { useRouter } from 'next/navigation';
import type { Route } from 'next';
import { type ReactNode, useEffect } from 'react';

import { PageLoader } from '@/components/feedback';
import { routes } from '@/config/routes';

import { useAuth } from './use-auth';

export interface AuthRouteGuardProps {
  children: ReactNode;
}

export function AuthRouteGuard({ children }: AuthRouteGuardProps) {
  const router = useRouter();
  const { isAuthenticated, isInitialized } = useAuth();

  useEffect(() => {
    if (isInitialized && isAuthenticated) {
      router.replace(routes.entries.path as Route);
    }
  }, [isAuthenticated, isInitialized, router]);

  if (!isInitialized || isAuthenticated) {
    return <PageLoader label="Restoring your session" />;
  }

  return children;
}

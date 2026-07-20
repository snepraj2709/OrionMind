import type { ReactNode } from 'react';

import { AuthRouteGuard } from '@/features/auth';

interface AuthenticationLayoutProps {
  children: ReactNode;
}

export default function AuthenticationLayout({
  children,
}: AuthenticationLayoutProps) {
  return <AuthRouteGuard>{children}</AuthRouteGuard>;
}

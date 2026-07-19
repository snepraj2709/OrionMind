import type { ReactNode } from 'react';

import { AuthProvider } from '@/features/auth';
import { getCurrentUser } from '@/services/auth';

interface AuthenticationLayoutProps {
  children: ReactNode;
}

export default async function AuthenticationLayout({
  children,
}: AuthenticationLayoutProps) {
  const user = await getCurrentUser();
  return <AuthProvider initialUser={user}>{children}</AuthProvider>;
}

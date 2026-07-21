import type { Metadata } from 'next';
import { routes, safeRedirectPath } from '@/config/routes';
import { LoginScreen } from '@/features/auth';

export const metadata: Metadata = { title: routes.login.label };

interface LoginPageProps {
  searchParams: Promise<{ returnTo?: string | string[] }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const requestedReturnTo = Array.isArray(params.returnTo)
    ? params.returnTo[0]
    : params.returnTo;
  const returnTo = requestedReturnTo
    ? safeRedirectPath(requestedReturnTo)
    : undefined;

  return <LoginScreen returnTo={returnTo} />;
}

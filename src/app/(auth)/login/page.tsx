import type { Metadata } from 'next';
import type { Route } from 'next';
import { redirect } from 'next/navigation';

import { AuthShell, BrandMark } from '@/components/layout';
import { pathWithRedirect, routes, safeRedirectPath } from '@/config/routes';
import { AuthRoutePrompt, SignInForm } from '@/features/auth';
import { getCurrentUser } from '@/services/auth';

export const metadata: Metadata = { title: routes.login.label };

interface LoginPageProps {
  searchParams: Promise<{ redirect?: string | string[] }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const requestedRedirect = Array.isArray(params.redirect)
    ? params.redirect[0]
    : params.redirect;
  const redirectTo = requestedRedirect
    ? safeRedirectPath(requestedRedirect)
    : undefined;
  const user = await getCurrentUser();

  if (user) redirect(safeRedirectPath(redirectTo) as Route);

  return (
    <AuthShell
      brand={<BrandMark />}
      description="Sign in to continue your practice."
      footer={
        <AuthRoutePrompt
          actionLabel="Register"
          href={pathWithRedirect(routes.signup.path, redirectTo) as Route}
          prompt="No account yet?"
        />
      }
      title="Welcome back"
      variant="prominent"
    >
      <SignInForm redirectTo={redirectTo} />
    </AuthShell>
  );
}

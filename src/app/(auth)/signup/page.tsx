import type { Metadata } from 'next';
import type { Route } from 'next';

import { AuthShell, BrandMark } from '@/components/layout';
import { pathWithRedirect, routes, safeRedirectPath } from '@/config/routes';
import { AuthRoutePrompt, SignUpForm } from '@/features/auth';

export const metadata: Metadata = { title: routes.signup.label };

interface SignupPageProps {
  searchParams: Promise<{ redirect?: string | string[] }>;
}

export default async function SignupPage({ searchParams }: SignupPageProps) {
  const params = await searchParams;
  const requestedRedirect = Array.isArray(params.redirect)
    ? params.redirect[0]
    : params.redirect;
  const redirectTo = requestedRedirect
    ? safeRedirectPath(requestedRedirect)
    : undefined;

  return (
    <AuthShell
      brand={<BrandMark />}
      description="A private space to know yourself better."
      footer={
        <AuthRoutePrompt
          actionLabel="Sign in"
          href={pathWithRedirect(routes.login.path, redirectTo) as Route}
          prompt="Already have one?"
        />
      }
      title="Begin your journal"
      variant="prominent"
    >
      <SignUpForm />
    </AuthShell>
  );
}

import type { Metadata } from 'next';
import type { Route } from 'next';
import { redirect } from 'next/navigation';

import { Typography } from '@/components/design-system';
import { AuthShell, BrandMark } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { pathWithRedirect, routes, safeRedirectPath } from '@/config/routes';
import { SignInForm } from '@/features/auth';
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
      description="Return to your private space for journaling and reflection."
      footer={
        <Typography className="text-muted-foreground" variant="bodySmall">
          New to Orion?{' '}
          <AppLink
            className="type-metadata"
            href={pathWithRedirect(routes.signup.path, redirectTo) as Route}
          >
            Create an account
          </AppLink>
        </Typography>
      }
      title={routes.login.label}
    >
      <SignInForm redirectTo={redirectTo} />
    </AuthShell>
  );
}

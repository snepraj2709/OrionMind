import type { Metadata } from 'next';
import type { Route } from 'next';
import { redirect } from 'next/navigation';

import { Typography } from '@/components/design-system';
import { AuthShell, BrandMark } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { pathWithRedirect, routes, safeRedirectPath } from '@/config/routes';
import { SignUpForm } from '@/features/auth';
import { getCurrentUser } from '@/services/auth';

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
  const user = await getCurrentUser();

  if (user) redirect(safeRedirectPath(redirectTo) as Route);

  return (
    <AuthShell
      brand={<BrandMark />}
      description="Create a private place for your entries and reflections."
      footer={
        <Typography className="text-muted-foreground" variant="bodySmall">
          Already have an account?{' '}
          <AppLink
            className="type-metadata"
            href={pathWithRedirect(routes.login.path, redirectTo) as Route}
          >
            Log in
          </AppLink>
        </Typography>
      }
      title={routes.signup.label}
    >
      <SignUpForm redirectTo={redirectTo} />
    </AuthShell>
  );
}

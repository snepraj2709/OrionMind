import type { Metadata, Route } from 'next';

import { Typography } from '@/components/design-system';
import { AuthShell, BrandMark } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { pathWithRedirect, routes, safeRedirectPath } from '@/config/routes';

export const metadata: Metadata = { title: routes.forgotPassword.label };

interface ForgotPasswordPageProps {
  searchParams: Promise<{ redirect?: string | string[] }>;
}

export default async function ForgotPasswordPage({
  searchParams,
}: ForgotPasswordPageProps) {
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
      description="Password recovery will connect to the production authentication provider."
      footer={
        <AppLink
          className="type-metadata"
          href={pathWithRedirect(routes.login.path, redirectTo) as Route}
        >
          Return to login
        </AppLink>
      }
      title={routes.forgotPassword.label}
    >
      <Typography className="text-muted-foreground" variant="body">
        Mock authentication does not send email. Your entries and account data
        have not been changed.
      </Typography>
    </AuthShell>
  );
}

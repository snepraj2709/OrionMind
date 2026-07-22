'use client';

import { AppButton, Typography } from '@/components/design-system';
import { AuthShell, BrandMark } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';

import { AuthRoutePrompt } from './auth-route-prompt';
import { SignUpForm } from './sign-up-form';
import { useAuth } from './use-auth';

export function SignupScreen() {
  const { flow, setFlow } = useAuth();

  if (flow === 'confirmation_email_sent') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="Supabase sent a confirmation link if the address can be registered."
        footer={<AppLink href={routes.login.path}>Return to login</AppLink>}
        title="Confirm your email"
      >
        <Typography
          className="text-muted-foreground"
          role="status"
          variant="body"
        >
          Open the newest confirmation link in this browser to finish signup.
        </Typography>
      </AuthShell>
    );
  }

  if (flow === 'confirmation_token_validation') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="Supabase is validating this one-time link."
        title="Validating confirmation link"
      >
        <Typography role="status" variant="body">
          Please wait…
        </Typography>
      </AuthShell>
    );
  }

  if (flow === 'expired_or_invalid_link') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="This confirmation link is expired, invalid, or already used."
        footer={<AppLink href={routes.login.path}>Return to login</AppLink>}
        title="Confirmation link invalid"
      >
        <AppButton className="w-full" onClick={() => setFlow('default')}>
          Try signup again
        </AppButton>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      brand={<BrandMark />}
      description="A private space to know yourself better."
      footer={
        <AuthRoutePrompt
          actionLabel="Sign in"
          href={routes.login.path}
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

'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { AppButton, Typography } from '@/components/design-system';
import {
  FormError,
  FormField,
  PasswordInput,
  SubmitButton,
  TextInput,
} from '@/components/forms';
import { AuthShell, BrandMark } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { resolvePostAuthPath, routes } from '@/config/routes';
import {
  passwordRecoverySchema,
  passwordUpdateSchema,
  type PasswordRecoveryInput,
  type PasswordUpdateInput,
} from '@/services/auth/schemas';

import { AuthRoutePrompt } from './auth-route-prompt';
import { SignInForm } from './sign-in-form';
import { useAuth } from './use-auth';

interface LoginScreenProps {
  returnTo?: string;
}

function RecoveryRequestForm() {
  const { isPending, requestPasswordReset } = useAuth();
  const [formError, setFormError] = useState<string>();
  const form = useForm<PasswordRecoveryInput>({
    resolver: zodResolver(passwordRecoverySchema),
    defaultValues: { email: '' },
  });

  const submit = form.handleSubmit(async (values) => {
    if (isPending) return;
    setFormError(undefined);
    const result = await requestPasswordReset(values);
    if (!result.ok) setFormError(result.error.message);
  });

  return (
    <form className="space-y-6" noValidate onSubmit={submit}>
      {formError ? <FormError>{formError}</FormError> : null}
      <FormField
        error={form.formState.errors.email?.message}
        id="recovery-email"
        label="Email"
        required
      >
        <TextInput
          autoComplete="email"
          inputMode="email"
          required
          type="email"
          {...form.register('email')}
        />
      </FormField>
      <SubmitButton
        className="w-full"
        loading={isPending}
        loadingLabel="Sending recovery email"
      >
        Send recovery email
      </SubmitButton>
    </form>
  );
}

function PasswordUpdateForm() {
  const { isPending, updatePassword } = useAuth();
  const [formError, setFormError] = useState<string>();
  const form = useForm<PasswordUpdateInput>({
    resolver: zodResolver(passwordUpdateSchema),
    defaultValues: { password: '', confirmation: '' },
  });

  const submit = form.handleSubmit(async (values) => {
    if (isPending) return;
    setFormError(undefined);
    const result = await updatePassword(values);
    if (!result.ok) setFormError(result.error.message);
  });

  return (
    <form className="space-y-6" noValidate onSubmit={submit}>
      {formError ? <FormError>{formError}</FormError> : null}
      <FormField
        error={form.formState.errors.password?.message}
        id="new-password"
        label="New password"
        required
      >
        <PasswordInput
          autoComplete="new-password"
          minLength={8}
          required
          {...form.register('password')}
        />
      </FormField>
      <FormField
        error={form.formState.errors.confirmation?.message}
        id="confirm-password"
        label="Confirm new password"
        required
      >
        <PasswordInput
          autoComplete="new-password"
          minLength={8}
          required
          {...form.register('confirmation')}
        />
      </FormField>
      <SubmitButton
        className="w-full"
        loading={isPending}
        loadingLabel="Updating password"
      >
        Update password
      </SubmitButton>
    </form>
  );
}

export function LoginScreen({ returnTo }: LoginScreenProps) {
  const router = useRouter();
  const { flow, setFlow } = useAuth();
  const recoverySearch = new URLSearchParams({ mode: 'forgot' });
  if (returnTo) recoverySearch.set('returnTo', returnTo);
  const recoveryHref = `${routes.login.path}?${recoverySearch}`;

  if (flow === 'forgot_password') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="We will send a recovery link to your email."
        footer={
          <AppButton onClick={() => setFlow('default')} variant="link">
            Return to login
          </AppButton>
        }
        title="Reset your password"
      >
        <RecoveryRequestForm />
      </AuthShell>
    );
  }

  if (flow === 'recovery_email_sent') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="If an account matches that address, a recovery link has been sent."
        footer={
          <AppButton onClick={() => setFlow('default')} variant="link">
            Return to login
          </AppButton>
        }
        title="Check your email"
      >
        <Typography
          className="text-muted-foreground"
          role="status"
          variant="body"
        >
          Open the newest recovery link once. Orion removes sensitive callback
          details after Supabase consumes them.
        </Typography>
      </AuthShell>
    );
  }

  if (flow === 'recovery_token_validation') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="Supabase is validating this one-time link."
        title="Validating recovery link"
      >
        <Typography role="status" variant="body">
          Please wait…
        </Typography>
      </AuthShell>
    );
  }

  if (flow === 'set_new_password') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="Choose a new password to finish account recovery."
        footer={<AppLink href={routes.home.path}>Cancel recovery</AppLink>}
        title="Set a new password"
      >
        <PasswordUpdateForm />
      </AuthShell>
    );
  }

  if (flow === 'recovery_complete') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="Your recovery is complete."
        title="Password updated"
      >
        <AppButton
          className="w-full"
          onClick={() => {
            setFlow('default');
            router.replace(resolvePostAuthPath(returnTo) as Route);
          }}
        >
          Continue to application
        </AppButton>
      </AuthShell>
    );
  }

  if (flow === 'expired_or_invalid_link') {
    return (
      <AuthShell
        brand={<BrandMark />}
        description="Recovery and confirmation links are time-limited and single use."
        footer={<AppLink href={routes.home.path}>Return home</AppLink>}
        title="This link is no longer valid"
      >
        <AppButton
          className="w-full"
          onClick={() => setFlow('forgot_password')}
        >
          Request a new recovery link
        </AppButton>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      brand={<BrandMark />}
      description="Sign in to continue your practice."
      footer={
        <AuthRoutePrompt
          actionLabel="Register"
          href={routes.signup.path}
          prompt="No account yet?"
        />
      }
      title="Welcome back"
      variant="prominent"
    >
      {flow === 'email_confirmed' ? (
        <Typography
          className="bg-secondary text-secondary-foreground radius-control mb-6 p-3"
          role="status"
          variant="bodySmall"
        >
          Your email is confirmed. Sign in to continue.
        </Typography>
      ) : null}
      {flow === 'session_expired' ? (
        <Typography
          className="bg-secondary text-secondary-foreground radius-control mb-6 p-3"
          role="status"
          variant="bodySmall"
        >
          Your session expired. Sign in again to continue.
        </Typography>
      ) : null}
      <SignInForm
        onForgotPassword={() => setFlow('forgot_password')}
        recoveryHref={recoveryHref}
      />
    </AuthShell>
  );
}

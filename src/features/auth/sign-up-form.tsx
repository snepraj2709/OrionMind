'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { MailCheck } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { Typography } from '@/components/design-system';
import { FormError } from '@/components/forms/form-error';
import { FormField } from '@/components/forms/form-field';
import { SubmitButton } from '@/components/forms/submit-button';
import { TextInput } from '@/components/forms/text-input';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';
import { signUpSchema, type SignUpInput } from '@/services/auth/schemas';

import { useAuth } from './use-auth';

export function SignUpForm() {
  const { isPending, signUp } = useAuth();
  const [formError, setFormError] = useState<string>();
  const [confirmationEmail, setConfirmationEmail] = useState<string>();
  const {
    formState: { errors },
    handleSubmit,
    register,
  } = useForm<SignUpInput>({
    resolver: zodResolver(signUpSchema),
    defaultValues: { name: '', email: '', password: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(undefined);
    const result = await signUp(values);
    if (!result.ok) {
      setFormError(result.error.message);
      return;
    }

    setConfirmationEmail(result.email);
  });

  if (confirmationEmail) {
    return (
      <div aria-live="polite" className="space-y-6 text-center" role="status">
        <div className="bg-secondary text-primary radius-pill mx-auto flex size-16 items-center justify-center">
          <MailCheck aria-hidden="true" className="size-6" />
        </div>
        <div className="space-y-2">
          <Typography as="h2" variant="componentTitle">
            Check your email
          </Typography>
          <Typography className="text-muted-foreground" variant="body">
            We sent a confirmation link to {confirmationEmail}. Open it to
            finish creating your account.
          </Typography>
        </div>
        <AppLink
          className="type-metadata underline underline-offset-4"
          href={routes.login.path}
        >
          Return to sign in
        </AppLink>
      </div>
    );
  }

  return (
    <form className="space-y-6" method="post" noValidate onSubmit={onSubmit}>
      {formError ? <FormError>{formError}</FormError> : null}
      <FormField
        error={errors.name?.message}
        id="name"
        label="Full name"
        required
      >
        <TextInput
          autoComplete="name"
          placeholder="Your name"
          {...register('name')}
        />
      </FormField>
      <FormField
        error={errors.email?.message}
        id="email"
        label="Email"
        required
      >
        <TextInput
          autoComplete="email"
          inputMode="email"
          placeholder="you@example.com"
          {...register('email')}
        />
      </FormField>
      <FormField
        description="Use at least 8 characters."
        error={errors.password?.message}
        id="password"
        label="Password"
        required
      >
        <TextInput
          autoComplete="new-password"
          type="password"
          {...register('password')}
        />
      </FormField>
      <SubmitButton
        className="w-full"
        loading={isPending}
        loadingLabel="Creating account"
      >
        Create account
      </SubmitButton>
    </form>
  );
}

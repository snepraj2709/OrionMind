'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import type { Route } from 'next';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { FormError } from '@/components/forms/form-error';
import { FormField } from '@/components/forms/form-field';
import { SubmitButton } from '@/components/forms/submit-button';
import { TextInput } from '@/components/forms/text-input';
import { AppLink } from '@/components/navigation';
import { pathWithRedirect, routes } from '@/config/routes';
import { signInSchema, type SignInInput } from '@/services/auth/schemas';

import { useAuth } from './use-auth';

export interface SignInFormProps {
  redirectTo?: string;
}

export function SignInForm({ redirectTo }: SignInFormProps) {
  const { isPending, signIn } = useAuth();
  const [formError, setFormError] = useState<string>();
  const {
    formState: { errors },
    handleSubmit,
    register,
  } = useForm<SignInInput>({
    resolver: zodResolver(signInSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(undefined);
    const result = await signIn(values);
    if (!result.ok) setFormError(result.error.message);
  });

  return (
    <form className="space-y-6" method="post" noValidate onSubmit={onSubmit}>
      {formError ? <FormError>{formError}</FormError> : null}
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
        error={errors.password?.message}
        id="password"
        label="Password"
        required
      >
        <TextInput
          autoComplete="current-password"
          type="password"
          {...register('password')}
        />
      </FormField>
      <div className="flex justify-end">
        <AppLink
          className="type-body-small"
          href={
            pathWithRedirect(routes.forgotPassword.path, redirectTo) as Route
          }
        >
          Forgot password?
        </AppLink>
      </div>
      <SubmitButton
        className="w-full"
        loading={isPending}
        loadingLabel="Signing in"
      >
        Sign in
      </SubmitButton>
    </form>
  );
}

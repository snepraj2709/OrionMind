'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import type { Route } from 'next';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { FormError } from '@/components/forms/form-error';
import { FormField } from '@/components/forms/form-field';
import { PasswordInput } from '@/components/forms/password-input';
import { SubmitButton } from '@/components/forms/submit-button';
import { TextInput } from '@/components/forms/text-input';
import { AppLink } from '@/components/navigation';
import { signInSchema, type SignInInput } from '@/services/auth/schemas';

import { useAuth } from './use-auth';

export interface SignInFormProps {
  onForgotPassword?: () => void;
  recoveryHref?: string;
}

export function SignInForm({
  onForgotPassword,
  recoveryHref = '/login?mode=forgot',
}: SignInFormProps) {
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
    if (isPending) return;
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
          required
          type="email"
          {...register('email')}
        />
      </FormField>
      <FormField
        error={errors.password?.message}
        id="password"
        label="Password"
        required
      >
        <PasswordInput
          autoComplete="current-password"
          required
          {...register('password')}
        />
      </FormField>
      <div className="flex justify-end">
        <AppLink
          className="type-body-small"
          href={recoveryHref as Route}
          onClick={onForgotPassword}
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

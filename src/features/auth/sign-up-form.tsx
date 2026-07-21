'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { FormError } from '@/components/forms/form-error';
import { FormField } from '@/components/forms/form-field';
import { SubmitButton } from '@/components/forms/submit-button';
import { TextInput } from '@/components/forms/text-input';
import { signUpSchema, type SignUpInput } from '@/services/auth/schemas';

import { useAuth } from './use-auth';

export function SignUpForm() {
  const { isPending, signUp } = useAuth();
  const [formError, setFormError] = useState<string>();
  const {
    formState: { errors },
    handleSubmit,
    register,
  } = useForm<SignUpInput>({
    resolver: zodResolver(signUpSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    if (isPending) return;
    setFormError(undefined);
    const result = await signUp(values);
    if (!result.ok) {
      setFormError(result.error.message);
      return;
    }
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
        description="Use at least 8 characters."
        error={errors.password?.message}
        id="password"
        label="Password"
        required
      >
        <TextInput
          autoComplete="new-password"
          minLength={8}
          required
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

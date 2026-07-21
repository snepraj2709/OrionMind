import type { AuthError } from '@supabase/supabase-js';

import type { AuthActionError } from './types';

type AuthOperation = 'sign-in' | 'sign-up' | 'recovery' | 'password-update';

const networkErrorNames = new Set([
  'AuthRetryableFetchError',
  'AuthUnknownError',
  'TypeError',
]);

function isAuthError(error: unknown): error is AuthError {
  return (
    error instanceof Error &&
    'status' in error &&
    typeof error.status === 'number'
  );
}

export function safeAuthActionError(
  error: unknown,
  operation: AuthOperation,
): AuthActionError {
  const code =
    error instanceof Error && 'code' in error && typeof error.code === 'string'
      ? error.code
      : undefined;
  const status = isAuthError(error) ? error.status : undefined;

  if (status === 429 || code?.includes('rate_limit')) {
    return {
      kind: 'rate_limited',
      message: 'Too many attempts. Wait a moment and try again.',
    };
  }

  if (operation === 'sign-in' && code === 'invalid_credentials') {
    return { kind: 'validation', message: 'Email or password is incorrect.' };
  }

  if (operation === 'sign-up' && code === 'weak_password') {
    return {
      kind: 'validation',
      message: 'Password does not meet the account requirements.',
    };
  }

  if (
    error instanceof TypeError ||
    (error instanceof Error && networkErrorNames.has(error.name))
  ) {
    return {
      kind: 'offline',
      message: 'Unable to connect. Check your connection and try again.',
    };
  }

  const message =
    operation === 'sign-in'
      ? 'Sign in is temporarily unavailable.'
      : operation === 'sign-up'
        ? 'Account creation is temporarily unavailable.'
        : operation === 'recovery'
          ? 'Password recovery is temporarily unavailable.'
          : 'Password update is temporarily unavailable.';
  return { kind: 'provider_error', message };
}

export function safeAuthErrorMessage(error: unknown, operation: AuthOperation) {
  return safeAuthActionError(error, operation).message;
}

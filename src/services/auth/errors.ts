import type { AuthError } from '@supabase/supabase-js';

type AuthOperation = 'sign-in' | 'sign-up';

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

export function safeAuthErrorMessage(error: unknown, operation: AuthOperation) {
  const code =
    error instanceof Error && 'code' in error && typeof error.code === 'string'
      ? error.code
      : undefined;
  const status = isAuthError(error) ? error.status : undefined;

  if (status === 429 || code?.includes('rate_limit')) {
    return 'Too many attempts. Wait a moment and try again.';
  }

  if (operation === 'sign-in' && code === 'invalid_credentials') {
    return 'Email or password is incorrect.';
  }

  if (operation === 'sign-up' && code === 'weak_password') {
    return 'Password does not meet the account requirements.';
  }

  if (
    error instanceof TypeError ||
    (error instanceof Error && networkErrorNames.has(error.name))
  ) {
    return 'Unable to connect. Check your connection and try again.';
  }

  return operation === 'sign-in'
    ? 'Sign in is temporarily unavailable.'
    : 'Account creation is temporarily unavailable.';
}

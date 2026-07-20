import { describe, expect, it } from 'vitest';

import { safeAuthErrorMessage } from './errors';

function authError(code: string, status = 400) {
  return Object.assign(new Error('Provider detail that must stay private.'), {
    code,
    status,
  });
}

describe('safeAuthErrorMessage', () => {
  it.each([
    [
      authError('invalid_credentials'),
      'sign-in' as const,
      'Email or password is incorrect.',
    ],
    [
      authError('over_email_send_rate_limit', 429),
      'sign-up' as const,
      'Too many attempts. Wait a moment and try again.',
    ],
    [
      authError('weak_password'),
      'sign-up' as const,
      'Password does not meet the account requirements.',
    ],
    [
      new TypeError('fetch failed'),
      'sign-in' as const,
      'Unable to connect. Check your connection and try again.',
    ],
    [
      new Error('unknown provider detail'),
      'sign-in' as const,
      'Sign in is temporarily unavailable.',
    ],
    [
      new Error('unknown provider detail'),
      'sign-up' as const,
      'Account creation is temporarily unavailable.',
    ],
  ])('maps provider failures to safe copy', (error, operation, expected) => {
    expect(safeAuthErrorMessage(error, operation)).toBe(expected);
    expect(safeAuthErrorMessage(error, operation)).not.toContain(
      'Provider detail',
    );
  });
});

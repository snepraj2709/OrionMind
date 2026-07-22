import type { EmailOtpType } from '@supabase/supabase-js';

import type { AuthFlow } from './types';

const sensitiveKeys = new Set([
  'access_token',
  'code',
  'expires_at',
  'expires_in',
  'provider_refresh_token',
  'provider_token',
  'refresh_token',
  'token',
  'token_hash',
  'token_type',
  'type',
  'error',
  'error_code',
  'error_description',
]);

const safeAuthKeys = new Set(['returnTo', 'state', 'mode']);

function normalizeSiteUrl(value: string) {
  const withProtocol = /^https?:\/\//i.test(value) ? value : `https://${value}`;
  const url = new URL(withProtocol);

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('The authentication site URL must use HTTP or HTTPS.');
  }

  return `${url.origin}/`;
}

export function createAuthRedirectUrl(
  path: string,
  browserOrigin: string = window.location.origin,
) {
  const configuredSiteUrl =
    process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
    process.env.NEXT_PUBLIC_VERCEL_URL?.trim() ||
    browserOrigin;

  return new URL(
    path.replace(/^\//, ''),
    normalizeSiteUrl(configuredSiteUrl),
  ).toString();
}

export type SupabaseAuthCallback =
  | { method: 'automatic' }
  | { method: 'verify_otp'; tokenHash: string; type: EmailOtpType };

function authParameters(location: Location) {
  return [
    new URLSearchParams(location.search),
    new URLSearchParams(location.hash.replace(/^#/, '')),
  ] as const;
}

export function readSupabaseAuthCallback(
  location: Location,
): SupabaseAuthCallback | null {
  const [search, hash] = authParameters(location);
  const value = (key: string) => search.get(key) ?? hash.get(key);
  const type = value('type');
  const code = value('code');
  const accessToken = value('access_token');
  const refreshToken = value('refresh_token');
  const tokenHash = value('token_hash');
  const isLogin = location.pathname === '/login';
  const isSignup = location.pathname === '/signup';

  if (!isLogin && !isSignup) return null;
  if (isLogin && type && type !== 'recovery') return null;
  if (isSignup && type && type !== 'signup' && type !== 'email') return null;

  if (code || (accessToken && refreshToken)) return { method: 'automatic' };
  if (!tokenHash) return null;

  if (isLogin) {
    return { method: 'verify_otp', tokenHash, type: 'recovery' };
  }
  return {
    method: 'verify_otp',
    tokenHash,
    type: type === 'email' ? 'email' : 'signup',
  };
}

export function readInitialAuthFlow(location: Location): AuthFlow {
  const [search, hash] = authParameters(location);
  const type = search.get('type') ?? hash.get('type');
  const callback = readSupabaseAuthCallback(location);

  if (search.has('error') || search.has('error_code') || hash.has('error')) {
    return 'expired_or_invalid_link';
  }
  if (type === 'recovery') {
    return callback && location.pathname === '/login'
      ? 'recovery_token_validation'
      : 'expired_or_invalid_link';
  }
  if (type === 'signup' || type === 'email') {
    return callback && location.pathname === '/signup'
      ? 'confirmation_token_validation'
      : 'expired_or_invalid_link';
  }
  if (callback && location.pathname === '/login') {
    return 'recovery_token_validation';
  }
  if (callback && location.pathname === '/signup') {
    return 'confirmation_token_validation';
  }
  if (callback) return 'expired_or_invalid_link';
  if (search.get('state') === 'session_expired') return 'session_expired';
  if (search.get('mode') === 'forgot') return 'forgot_password';
  return 'default';
}

export function hasSensitiveAuthMaterial(location: Location) {
  const [search, hash] = authParameters(location);
  return [...sensitiveKeys].some((key) => search.has(key) || hash.has(key));
}

export function scrubSensitiveAuthMaterial(
  location: Location,
  history: History,
) {
  if (!hasSensitiveAuthMaterial(location)) return;

  const current = new URL(location.href);
  const safeSearch = new URLSearchParams();
  for (const [key, value] of current.searchParams) {
    if (safeAuthKeys.has(key)) safeSearch.set(key, value);
  }
  const search = safeSearch.toString();
  history.replaceState(
    history.state,
    '',
    `${current.pathname}${search ? `?${search}` : ''}`,
  );
}

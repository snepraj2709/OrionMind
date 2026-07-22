import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createAuthRedirectUrl,
  hasSensitiveAuthMaterial,
  readInitialAuthFlow,
  readSupabaseAuthCallback,
  scrubSensitiveAuthMaterial,
} from './auth-url';

afterEach(() => {
  window.history.replaceState({}, '', '/');
  vi.unstubAllEnvs();
});

describe('Supabase auth URL handling', () => {
  it('uses the canonical production site URL for email callbacks', () => {
    vi.stubEnv('NEXT_PUBLIC_SITE_URL', 'https://www.orionmind.in');
    vi.stubEnv('NEXT_PUBLIC_VERCEL_URL', 'preview.vercel.app');

    expect(createAuthRedirectUrl('/signup', 'http://localhost:3000')).toBe(
      'https://www.orionmind.in/signup',
    );
  });

  it('supports Vercel deployment URLs and local browser fallback', () => {
    vi.stubEnv('NEXT_PUBLIC_VERCEL_URL', 'preview.vercel.app');
    expect(createAuthRedirectUrl('/login', 'http://localhost:3000')).toBe(
      'https://preview.vercel.app/login',
    );

    vi.stubEnv('NEXT_PUBLIC_VERCEL_URL', '');
    expect(createAuthRedirectUrl('/signup', 'http://localhost:3000')).toBe(
      'http://localhost:3000/signup',
    );
  });

  it('detects and removes callback credentials while retaining safe auth state', () => {
    window.history.replaceState(
      {},
      '',
      '/login?returnTo=%2Fjourney&type=recovery&error_description=private#access_token=sensitive&refresh_token=sensitive',
    );

    expect(hasSensitiveAuthMaterial(window.location)).toBe(true);
    scrubSensitiveAuthMaterial(window.location, window.history);

    expect(window.location.pathname).toBe('/login');
    expect(window.location.search).toBe('?returnTo=%2Fjourney');
    expect(window.location.hash).toBe('');
  });

  it.each(['/#privacy', '/#terms'])(
    'preserves non-auth landing anchor %s',
    (path) => {
      window.history.replaceState({}, '', path);
      scrubSensitiveAuthMaterial(window.location, window.history);
      expect(`${window.location.pathname}${window.location.hash}`).toBe(path);
    },
  );

  it('recognizes PKCE, implicit, and token-hash callbacks on their correct routes', () => {
    window.history.replaceState({}, '', '/signup?code=one-time-code');
    expect(readSupabaseAuthCallback(window.location)).toEqual({
      method: 'automatic',
    });
    expect(readInitialAuthFlow(window.location)).toBe(
      'confirmation_token_validation',
    );

    window.history.replaceState(
      {},
      '',
      '/login#access_token=access&refresh_token=refresh&type=recovery',
    );
    expect(readSupabaseAuthCallback(window.location)).toEqual({
      method: 'automatic',
    });

    window.history.replaceState(
      {},
      '',
      '/signup?token_hash=one-time-hash&type=signup',
    );
    expect(readSupabaseAuthCallback(window.location)).toEqual({
      method: 'verify_otp',
      tokenHash: 'one-time-hash',
      type: 'signup',
    });
  });

  it.each([
    '/signup?type=signup',
    '/signup?code=one-time-code&type=recovery',
    '/login?token_hash=one-time-hash&type=signup',
    '/entries?code=one-time-code&type=recovery',
  ])('rejects incomplete or wrong-route callback %s', (path) => {
    window.history.replaceState({}, '', path);
    expect(readSupabaseAuthCallback(window.location)).toBeNull();
    expect(readInitialAuthFlow(window.location)).toBe(
      'expired_or_invalid_link',
    );
  });
});

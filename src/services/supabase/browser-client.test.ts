import { afterEach, describe, expect, it, vi } from 'vitest';

interface BrowserClientOptions {
  auth: {
    autoRefreshToken: boolean;
    detectSessionInUrl: (
      url: URL,
      parameters: Record<string, string>,
    ) => boolean;
    flowType: 'implicit';
    persistSession: boolean;
    storage: Pick<Storage, 'getItem' | 'removeItem' | 'setItem'>;
  };
}

const supabaseMocks = vi.hoisted(() => ({
  createClient: vi.fn(
    (_url: string, _key: string, _options: BrowserClientOptions) => {
      void _url;
      void _key;
      void _options;
      return { auth: {} };
    },
  ),
}));

vi.mock('@supabase/supabase-js', () => ({
  createClient: supabaseMocks.createClient,
}));

import {
  createSupabaseBrowserClient,
  resolveSupabaseBrowserClient,
} from './browser-client';

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.unstubAllEnvs();
  supabaseMocks.createClient.mockClear();
});

describe('createSupabaseBrowserClient', () => {
  it('uses only the public environment configuration and supplied session storage', () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://project.supabase.co');
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', 'publishable-key');

    const storage = window.sessionStorage;
    const client = createSupabaseBrowserClient(storage);

    expect(client).toEqual({ auth: {} });
    expect(supabaseMocks.createClient).toHaveBeenCalledWith(
      'https://project.supabase.co',
      'publishable-key',
      {
        auth: {
          autoRefreshToken: true,
          detectSessionInUrl: expect.any(Function),
          flowType: 'implicit',
          persistSession: true,
          storage,
        },
      },
    );

    const options = supabaseMocks.createClient.mock.calls[0]?.[2];
    const detectSessionInUrl = options?.auth?.detectSessionInUrl;
    expect(detectSessionInUrl).toBeTypeOf('function');
    if (typeof detectSessionInUrl !== 'function') return;

    expect(
      detectSessionInUrl(new URL('https://orion.test/login'), {
        access_token: 'private',
        refresh_token: 'private',
        type: 'signup',
      }),
    ).toBe(false);
    expect(
      detectSessionInUrl(new URL('https://orion.test/signup'), {
        access_token: 'private',
        refresh_token: 'private',
        type: 'signup',
      }),
    ).toBe(true);
    expect(
      detectSessionInUrl(new URL('https://orion.test/profile'), {
        access_token: 'private',
        refresh_token: 'private',
        type: 'recovery',
      }),
    ).toBe(false);
  });

  it('does not construct a browser client during server rendering', () => {
    vi.stubGlobal('window', undefined);

    expect(resolveSupabaseBrowserClient(undefined)).toBeNull();
    expect(supabaseMocks.createClient).not.toHaveBeenCalled();
  });
});

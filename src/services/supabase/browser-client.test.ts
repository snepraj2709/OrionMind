import { afterEach, describe, expect, it, vi } from 'vitest';

const supabaseMocks = vi.hoisted(() => ({
  createClient: vi.fn(() => ({ auth: {} })),
}));

vi.mock('@supabase/supabase-js', () => ({
  createClient: supabaseMocks.createClient,
}));

import { createSupabaseBrowserClient } from './browser-client';

afterEach(() => {
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
          detectSessionInUrl: true,
          persistSession: true,
          storage,
        },
      },
    );
  });
});

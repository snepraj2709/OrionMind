import { createClient, type SupabaseClient } from '@supabase/supabase-js';

import { getSupabasePublicConfig } from '@/config/supabase';

let browserClient: SupabaseClient | undefined;

export function createSupabaseBrowserClient(storage: Storage) {
  const { publishableKey, url } = getSupabasePublicConfig();

  return createClient(url, publishableKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: true,
      persistSession: true,
      storage,
    },
  });
}

export function getSupabaseBrowserClient() {
  if (typeof window === 'undefined') {
    throw new Error('The Supabase browser client requires a browser.');
  }

  browserClient ??= createSupabaseBrowserClient(window.sessionStorage);
  return browserClient;
}

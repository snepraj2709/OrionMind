import { createClient, type SupabaseClient } from '@supabase/supabase-js';

import {
  getSupabasePublicConfig,
  SupabaseConfigurationError,
} from '@/config/supabase';

let browserClient: SupabaseClient | undefined;

function shouldDetectSessionInUrl(
  url: URL,
  parameters: Record<string, string>,
) {
  const pathname = url.pathname.replace(/\/$/, '') || '/';
  const isLogin = pathname === '/login';
  const isSignup = pathname === '/signup';
  const callbackType = parameters.type;

  if (!isLogin && !isSignup) return false;
  if (callbackType === 'recovery') return isLogin;
  if (callbackType === 'signup' || callbackType === 'email') return isSignup;
  return true;
}

export function createSupabaseBrowserClient(storage: Storage) {
  const { publishableKey, url } = getSupabasePublicConfig();

  return createClient(url, publishableKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: shouldDetectSessionInUrl,
      flowType: 'pkce',
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

export function resolveSupabaseBrowserClient(
  suppliedClient: SupabaseClient | null | undefined,
) {
  if (suppliedClient !== undefined) return suppliedClient;
  if (typeof window === 'undefined') return null;

  try {
    return getSupabaseBrowserClient();
  } catch (error) {
    if (error instanceof SupabaseConfigurationError) return null;
    throw error;
  }
}

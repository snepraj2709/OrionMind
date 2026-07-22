import {
  createClient,
  type SupabaseClient,
  type SupportedStorage,
} from '@supabase/supabase-js';

import {
  getSupabasePublicConfig,
  SupabaseConfigurationError,
} from '@/config/supabase';

let browserClient: SupabaseClient | undefined;

function createAuthStorage(
  tabStorage: Storage,
  crossTabStorage: Storage,
): SupportedStorage {
  const storageFor = (key: string) =>
    key.endsWith('-code-verifier') ? crossTabStorage : tabStorage;

  return {
    getItem: (key) => storageFor(key).getItem(key),
    removeItem: (key) => storageFor(key).removeItem(key),
    setItem: (key, value) => storageFor(key).setItem(key, value),
  };
}

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
      storage: createAuthStorage(storage, window.localStorage),
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

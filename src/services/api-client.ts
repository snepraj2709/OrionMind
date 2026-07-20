import { resolveApiUrl } from '@/config/api';
import { getSupabaseBrowserClient } from '@/services/supabase';

export type ApiRequest = (
  path: string,
  init?: RequestInit,
) => Promise<Response>;

export const apiRequest: ApiRequest = async (path, init) => {
  const supabase = getSupabaseBrowserClient();
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();

  if (error) {
    throw new Error('Unable to restore the authenticated session.');
  }

  const headers = new Headers(init?.headers);

  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`);
  }

  return fetch(resolveApiUrl(path), {
    ...init,
    headers,
  });
};

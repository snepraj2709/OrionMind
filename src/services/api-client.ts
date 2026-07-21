import type { SupabaseClient } from '@supabase/supabase-js';

import { apiConfig } from '@/config/api';
import { getSupabaseBrowserClient } from '@/services/supabase';

export type ApiRequest = (
  path: string,
  init?: RequestInit,
) => Promise<Response>;

export class SessionExpiredError extends Error {
  constructor() {
    super('The authenticated session expired.');
    this.name = 'SessionExpiredError';
  }
}

export class UntrustedApiRequestError extends Error {
  constructor() {
    super(
      'Authenticated requests are restricted to the configured /api/v1 boundary.',
    );
    this.name = 'UntrustedApiRequestError';
  }
}

interface AuthorizedApiRequestOptions {
  client: SupabaseClient;
  onSessionExpired: () => void | Promise<void>;
  fetchImplementation?: typeof fetch;
  apiBaseUrl?: string;
}

function browserOrigin() {
  return typeof window === 'undefined'
    ? 'http://localhost'
    : window.location.origin;
}

export function createAuthorizedApiRequest({
  client,
  onSessionExpired,
  fetchImplementation = fetch,
  apiBaseUrl = apiConfig.baseUrl,
}: AuthorizedApiRequestOptions): ApiRequest {
  let coordinatedRefresh: ReturnType<typeof client.auth.refreshSession> | null =
    null;
  const configuredOrigin = new URL(apiBaseUrl || '/', browserOrigin()).origin;

  function trustedUrl(path: string) {
    const isAbsolute = /^[A-Za-z][A-Za-z\d+.-]*:/.test(path);
    const requestUrl = isAbsolute
      ? new URL(path)
      : new URL(path, apiBaseUrl || browserOrigin());
    const canonicalPath =
      requestUrl.pathname === '/api/v1' ||
      requestUrl.pathname.startsWith('/api/v1/');

    if (requestUrl.origin !== configuredOrigin || !canonicalPath) {
      throw new UntrustedApiRequestError();
    }
    return requestUrl;
  }

  async function expireSession(): Promise<never> {
    await onSessionExpired();
    throw new SessionExpiredError();
  }

  async function refreshAccessToken() {
    coordinatedRefresh ??= client.auth.refreshSession();
    try {
      const { data, error } = await coordinatedRefresh;
      return error ? null : (data.session?.access_token ?? null);
    } finally {
      coordinatedRefresh = null;
    }
  }

  async function send(request: Request, accessToken: string) {
    const headers = new Headers(request.headers);
    headers.set('Authorization', `Bearer ${accessToken}`);
    return fetchImplementation(new Request(request, { headers }));
  }

  return async (path, init) => {
    const requestUrl = trustedUrl(path);
    const request = new Request(requestUrl, init);
    const { data, error } = await client.auth.getSession();
    const initialToken = error ? null : data.session?.access_token;
    if (!initialToken) return expireSession();

    const firstResponse = await send(request.clone(), initialToken);
    if (firstResponse.status !== 401) return firstResponse;

    const refreshedToken = await refreshAccessToken();
    if (!refreshedToken) return expireSession();

    const replayResponse = await send(request.clone(), refreshedToken);
    if (replayResponse.status === 401) return expireSession();
    return replayResponse;
  };
}

let sessionExpiredHandler: () => void | Promise<void> = () => undefined;
let sharedApiRequest: ApiRequest | undefined;

export function setApiSessionExpiredHandler(
  handler: () => void | Promise<void>,
) {
  sessionExpiredHandler = handler;
  return () => {
    if (sessionExpiredHandler === handler) {
      sessionExpiredHandler = () => undefined;
    }
  };
}

export const apiRequest: ApiRequest = (path, init) => {
  sharedApiRequest ??= createAuthorizedApiRequest({
    client: getSupabaseBrowserClient(),
    onSessionExpired: () => sessionExpiredHandler(),
  });
  return sharedApiRequest(path, init);
};

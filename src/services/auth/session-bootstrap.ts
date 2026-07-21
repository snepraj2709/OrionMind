import type { EmailOtpType, SupabaseClient } from '@supabase/supabase-js';

type SessionResult = Awaited<ReturnType<SupabaseClient['auth']['getSession']>>;

const sessionPromises = new WeakMap<SupabaseClient, Promise<SessionResult>>();
const callbackPromises = new WeakMap<
  SupabaseClient,
  Map<string, Promise<unknown>>
>();

export function getInitialSessionOnce(client: SupabaseClient) {
  const existing = sessionPromises.get(client);
  if (existing) return existing;

  const request = client.auth.getSession();
  sessionPromises.set(client, request);
  return request;
}

function callbackOnce<T>(
  client: SupabaseClient,
  key: string,
  request: () => Promise<T>,
) {
  const requests = callbackPromises.get(client) ?? new Map();
  callbackPromises.set(client, requests);
  const existing = requests.get(key) as Promise<T> | undefined;
  if (existing) return existing;

  const pending = request();
  requests.set(key, pending);
  return pending;
}

export function initializeAuthCallbackOnce(client: SupabaseClient) {
  return callbackOnce(client, 'automatic', () => client.auth.initialize());
}

export function verifyAuthOtpOnce(
  client: SupabaseClient,
  tokenHash: string,
  type: EmailOtpType,
) {
  return callbackOnce(client, `${type}:${tokenHash}`, () =>
    client.auth.verifyOtp({ token_hash: tokenHash, type }),
  );
}

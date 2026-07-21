import type { SupabaseClient } from '@supabase/supabase-js';
import { describe, expect, it, vi } from 'vitest';

import {
  createAuthorizedApiRequest,
  SessionExpiredError,
  UntrustedApiRequestError,
} from './api-client';

function clientWithTokens(initial = 'first', refreshed = 'second') {
  const refreshSession = vi.fn(() =>
    Promise.resolve({
      data: { session: { access_token: refreshed }, user: {} },
      error: null,
    }),
  );
  const client = {
    auth: {
      getSession: vi.fn(() =>
        Promise.resolve({
          data: { session: { access_token: initial } },
          error: null,
        }),
      ),
      refreshSession,
    },
  } as unknown as SupabaseClient;
  return { client, refreshSession };
}

describe('authorized API requests', () => {
  it('adds the current bearer token and preserves headers and bodies', async () => {
    const { client } = clientWithTokens();
    const fetchImplementation = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ ok: true }));
    const request = createAuthorizedApiRequest({
      client,
      onSessionExpired: vi.fn(),
      fetchImplementation,
      apiBaseUrl: 'https://api.orion.test',
    });

    await request('/api/v1/entries', {
      method: 'POST',
      headers: { Accept: 'application/json', Authorization: 'stale-token' },
      body: JSON.stringify({ content: 'preserved' }),
    });

    const sent = fetchImplementation.mock.calls[0]?.[0] as Request;
    expect(sent.url).toBe('https://api.orion.test/api/v1/entries');
    expect(sent.headers.get('Accept')).toBe('application/json');
    expect(sent.headers.get('Authorization')).toBe('Bearer first');
    expect(await sent.text()).toBe('{"content":"preserved"}');
  });

  it('coordinates one refresh and replays a 401 once', async () => {
    const { client, refreshSession } = clientWithTokens();
    const fetchImplementation = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response('ok', { status: 200 }));
    const onSessionExpired = vi.fn();
    const request = createAuthorizedApiRequest({
      client,
      onSessionExpired,
      fetchImplementation,
      apiBaseUrl: 'https://api.orion.test',
    });

    await expect(request('/api/v1/profile')).resolves.toHaveProperty(
      'status',
      200,
    );
    expect(refreshSession).toHaveBeenCalledOnce();
    expect(fetchImplementation).toHaveBeenCalledTimes(2);
    expect(
      (fetchImplementation.mock.calls[1]?.[0] as Request).headers.get(
        'Authorization',
      ),
    ).toBe('Bearer second');
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  it('expires after a second 401 or failed refresh', async () => {
    const first = clientWithTokens();
    const onSecond401 = vi.fn();
    const second401Request = createAuthorizedApiRequest({
      client: first.client,
      onSessionExpired: onSecond401,
      fetchImplementation: vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response(null, { status: 401 })),
      apiBaseUrl: 'https://api.orion.test',
    });
    await expect(second401Request('/api/v1/profile')).rejects.toBeInstanceOf(
      SessionExpiredError,
    );
    expect(onSecond401).toHaveBeenCalledOnce();

    const refreshSession = vi.fn(() =>
      Promise.resolve({
        data: { session: null, user: null },
        error: new Error('private'),
      }),
    );
    const noRefreshClient = {
      auth: {
        getSession: vi.fn(() =>
          Promise.resolve({
            data: { session: { access_token: 'first' } },
            error: null,
          }),
        ),
        refreshSession,
      },
    } as unknown as SupabaseClient;
    const onRefreshFailure = vi.fn();
    const refreshFailureRequest = createAuthorizedApiRequest({
      client: noRefreshClient,
      onSessionExpired: onRefreshFailure,
      fetchImplementation: vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response(null, { status: 401 })),
      apiBaseUrl: 'https://api.orion.test',
    });
    await expect(
      refreshFailureRequest('/api/v1/profile'),
    ).rejects.toBeInstanceOf(SessionExpiredError);
    expect(onRefreshFailure).toHaveBeenCalledOnce();
  });

  it('shares one refresh across concurrent 401 responses', async () => {
    let releaseRefresh: (() => void) | undefined;
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    const refreshSession = vi.fn(async () => {
      await refreshGate;
      return {
        data: { session: { access_token: 'second' }, user: {} },
        error: null,
      };
    });
    const client = {
      auth: {
        getSession: vi.fn(() =>
          Promise.resolve({
            data: { session: { access_token: 'first' } },
            error: null,
          }),
        ),
        refreshSession,
      },
    } as unknown as SupabaseClient;
    const fetchImplementation = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValue(new Response('ok', { status: 200 }));
    const request = createAuthorizedApiRequest({
      client,
      onSessionExpired: vi.fn(),
      fetchImplementation,
      apiBaseUrl: 'https://api.orion.test',
    });

    const requests = [request('/api/v1/profile'), request('/api/v1/entries')];
    await vi.waitFor(() => expect(refreshSession).toHaveBeenCalledOnce());
    releaseRefresh?.();

    await expect(Promise.all(requests)).resolves.toHaveLength(2);
    expect(refreshSession).toHaveBeenCalledOnce();
    expect(fetchImplementation).toHaveBeenCalledTimes(4);
  });

  it('expires before fetch when no session exists', async () => {
    const client = {
      auth: {
        getSession: vi.fn(() =>
          Promise.resolve({ data: { session: null }, error: null }),
        ),
        refreshSession: vi.fn(),
      },
    } as unknown as SupabaseClient;
    const fetchImplementation = vi.fn<typeof fetch>();
    const onSessionExpired = vi.fn();
    const request = createAuthorizedApiRequest({
      client,
      onSessionExpired,
      fetchImplementation,
      apiBaseUrl: 'https://api.orion.test',
    });

    await expect(request('/api/v1/profile')).rejects.toBeInstanceOf(
      SessionExpiredError,
    );
    expect(fetchImplementation).not.toHaveBeenCalled();
    expect(onSessionExpired).toHaveBeenCalledOnce();
  });

  it.each([
    'https://attacker.test/api/v1/profile',
    'https://api.orion.test/api/profile',
    '/api/profile',
  ])(
    'rejects untrusted destination %s before reading a token',
    async (path) => {
      const { client } = clientWithTokens();
      const fetchImplementation = vi.fn<typeof fetch>();
      const request = createAuthorizedApiRequest({
        client,
        onSessionExpired: vi.fn(),
        fetchImplementation,
        apiBaseUrl: 'https://api.orion.test',
      });

      await expect(request(path)).rejects.toBeInstanceOf(
        UntrustedApiRequestError,
      );
      expect(client.auth.getSession).not.toHaveBeenCalled();
      expect(fetchImplementation).not.toHaveBeenCalled();
    },
  );
});

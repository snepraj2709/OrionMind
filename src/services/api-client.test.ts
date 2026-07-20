import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from './api-client';

const supabaseMocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/services/supabase', () => ({
  getSupabaseBrowserClient: () => ({
    auth: { getSession: supabaseMocks.getSession },
  }),
}));

afterEach(() => {
  vi.restoreAllMocks();
  supabaseMocks.getSession.mockReset();
});

describe('apiRequest', () => {
  it('adds the current bearer token and does not invent a GET body', async () => {
    supabaseMocks.getSession.mockResolvedValue({
      data: { session: { access_token: 'test-access-token' } },
      error: null,
    });
    const request = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(Response.json({ ok: true }));

    await apiRequest('/api/v1/reflection?reflectionTab=hiddenDriver');

    const [url, init] = request.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/reflection?reflectionTab=hiddenDriver');
    expect(new Headers(init?.headers).get('Authorization')).toBe(
      'Bearer test-access-token',
    );
    expect(init).not.toHaveProperty('body');
    expect(init).not.toHaveProperty('credentials');
  });

  it('preserves caller headers while applying the authenticated token', async () => {
    supabaseMocks.getSession.mockResolvedValue({
      data: { session: { access_token: 'test-access-token' } },
      error: null,
    });
    const request = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(Response.json({ ok: true }));

    await apiRequest('/api/v1/entries', {
      headers: { Accept: 'application/json', Authorization: 'stale-token' },
    });

    const headers = new Headers(request.mock.calls[0]?.[1]?.headers);
    expect(headers.get('Accept')).toBe('application/json');
    expect(headers.get('Authorization')).toBe('Bearer test-access-token');
  });

  it('omits Authorization when there is no active session', async () => {
    supabaseMocks.getSession.mockResolvedValue({
      data: { session: null },
      error: null,
    });
    const request = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(Response.json({ ok: true }));

    await apiRequest('/api/v1/entries');

    const headers = new Headers(request.mock.calls[0]?.[1]?.headers);
    expect(headers.has('Authorization')).toBe(false);
  });
});

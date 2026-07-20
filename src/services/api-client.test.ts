import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from './api-client';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('apiRequest', () => {
  it('includes session credentials and does not invent a GET body', async () => {
    const request = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(Response.json({ ok: true }));

    await apiRequest('/api/v1/reflection?reflectionTab=hiddenDriver');

    expect(request).toHaveBeenCalledWith(
      '/api/v1/reflection?reflectionTab=hiddenDriver',
      {
        credentials: 'include',
      },
    );
    expect(request.mock.calls[0]?.[1]).not.toHaveProperty('body');
  });
});

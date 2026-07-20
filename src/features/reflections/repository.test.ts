import { describe, expect, it, vi } from 'vitest';

import { reflectionEntryFixtures } from './fixtures';
import { HttpReflectionsRepository } from './repository';
import { buildReflectionApiResponse } from './response-builder';

describe('HttpReflectionsRepository', () => {
  it('sends the user, active tab, and range to the endpoint', async () => {
    const body = buildReflectionApiResponse({
      entries: reflectionEntryFixtures,
      range: '30d',
      reflectionTab: 'recurringLoop',
      totalAvailable: reflectionEntryFixtures.length,
      userId: 'reader id',
    });
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(body));
    const repository = new HttpReflectionsRepository(request);

    await repository.getReflection({
      userId: 'reader id',
      reflectionTab: 'recurringLoop',
      range: '30d',
    });

    const requestUrl = new URL(
      String(request.mock.calls[0]?.[0]),
      'http://localhost',
    );
    expect(requestUrl.pathname).toBe('/api/v1/reflection');
    expect(Object.fromEntries(requestUrl.searchParams)).toEqual({
      userId: 'reader id',
      reflectionTab: 'recurringLoop',
      range: '30d',
    });
  });

  it('rejects failed and malformed responses', async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 403 }))
      .mockResolvedValueOnce(Response.json({ reflectionTab: 'hiddenDriver' }));
    const repository = new HttpReflectionsRepository(request);
    const input = {
      userId: 'reader-id',
      reflectionTab: 'hiddenDriver',
      range: 'all',
    } as const;

    await expect(repository.getReflection(input)).rejects.toThrow(
      'Reflection request failed: 403',
    );
    await expect(repository.getReflection(input)).rejects.toThrow();
  });
});

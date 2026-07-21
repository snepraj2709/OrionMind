import { describe, expect, it, vi } from 'vitest';

import { reflectionApiFixture, reflectionFixtureIds } from './fixtures';
import { HttpReflectionsRepository } from './repository';

describe('HttpReflectionsRepository', () => {
  it('sends only range to the plural aggregate endpoint', async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(reflectionApiFixture));
    const repository = new HttpReflectionsRepository(request);

    await repository.getReflection({ range: '30d' });

    const url = new URL(String(request.mock.calls[0]?.[0]), 'http://localhost');
    expect(url.pathname).toBe('/api/v1/reflections');
    expect(Object.fromEntries(url.searchParams)).toEqual({ range: '30d' });
    expect(url.searchParams.has('userId')).toBe(false);
    expect(url.searchParams.has('reflectionTab')).toBe(false);
  });

  it('writes strict feedback to the owner-derived insight endpoint', async () => {
    const result = {
      snapshotId: reflectionFixtureIds.snapshot,
      insightId: reflectionFixtureIds.hiddenDriver,
      response: 'rejected' as const,
      updatedAt: '2026-07-21T12:42:00Z',
    };
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(result));
    const repository = new HttpReflectionsRepository(request);

    await expect(
      repository.putFeedback({
        snapshotId: result.snapshotId,
        insightId: result.insightId,
        response: result.response,
      }),
    ).resolves.toEqual(result);

    expect(request).toHaveBeenCalledWith(
      `/api/v1/reflections/${result.snapshotId}/insights/${result.insightId}/feedback`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ response: 'rejected' }),
      },
    );
  });

  it.each([401, 422, 503])(
    'rejects a non-success GET response with status %s before parsing',
    async (status) => {
      const request = vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response(null, { status }));
      const repository = new HttpReflectionsRepository(request);

      await expect(repository.getReflection({ range: 'all' })).rejects.toThrow(
        `Reflection request failed: ${status}`,
      );
    },
  );

  it('rejects malformed GET and failed or malformed feedback responses', async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ range: 'all' }))
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(Response.json({ response: 'rejected' }));
    const repository = new HttpReflectionsRepository(request);
    const feedbackInput = {
      snapshotId: reflectionFixtureIds.snapshot,
      insightId: reflectionFixtureIds.hiddenDriver,
      response: 'rejected' as const,
    };

    await expect(repository.getReflection({ range: 'all' })).rejects.toThrow();
    await expect(repository.putFeedback(feedbackInput)).rejects.toThrow(
      'Reflection feedback failed: 404',
    );
    await expect(repository.putFeedback(feedbackInput)).rejects.toThrow();
  });
});

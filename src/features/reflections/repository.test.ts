import { afterEach, describe, expect, it, vi } from 'vitest';

import demoReflection from '../../../data/orion_30_day_reflection_analysis.json';

import { reflectionApiFixture, reflectionFixtureIds } from './fixtures';
import { HttpReflectionsRepository, reflectionsRepository } from './repository';

describe('reflectionsRepository', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('serves the complete hardcoded fixture for every range without calling fetch', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValue(new Error('The reflections API must not be called'));

    const allResult = await reflectionsRepository.getReflection({
      range: 'all',
    });
    const sevenDayResult = await reflectionsRepository.getReflection({
      range: '7d',
    });

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(allResult.range).toBe('all');
    expect(sevenDayResult.range).toBe('7d');
    expect(allResult.data.hiddenDriver).toMatchObject({
      status: 'available',
      statement: demoReflection.data.hiddenDriver.statement,
    });
    expect(allResult.data.hiddenDriver).not.toBe(
      sevenDayResult.data.hiddenDriver,
    );
    expect(allResult.data.hiddenDriver.status).toBe('available');
    expect(allResult.data.recurringLoop.status).toBe('available');
    expect(allResult.data.innerTensions.status).toBe('available');
    if (
      allResult.data.hiddenDriver.status === 'available' &&
      allResult.data.recurringLoop.status === 'available' &&
      allResult.data.innerTensions.status === 'available'
    ) {
      expect(allResult.data.hiddenDriver.evidence).toHaveLength(8);
      expect(allResult.data.recurringLoop.steps).toHaveLength(6);
      expect(allResult.data.innerTensions.tensions).toHaveLength(3);
    }
  });

  it('keeps feedback in the frontend session without calling fetch', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValue(new Error('The reflections API must not be called'));
    const initial = await reflectionsRepository.getReflection({ range: '30d' });
    const insight = initial.data.hiddenDriver;

    expect(initial.snapshot).not.toBeNull();
    expect(insight.status).toBe('available');
    if (!initial.snapshot || insight.status !== 'available') return;

    await reflectionsRepository.putFeedback({
      snapshotId: initial.snapshot.id,
      insightId: insight.id,
      response: 'resonates',
    });
    const refreshed = await reflectionsRepository.getReflection({
      range: '30d',
    });

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(refreshed.data.hiddenDriver).toMatchObject({
      status: 'available',
      feedback: 'resonates',
    });
  });
});

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

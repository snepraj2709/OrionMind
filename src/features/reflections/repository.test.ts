import { afterEach, describe, expect, it, vi } from 'vitest';

import demoReflection from '../../../data/orion_30_day_reflection_analysis.json';

import { reflectionApiFixture, reflectionFixtureIds } from './fixtures';
import { fixtureReflectionsRepository } from './fixture-repository';
import {
  HttpReflectionsRepository,
  ReflectionRequestError,
  reflectionsRepository,
} from './repository';

describe('reflectionsRepository', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uses the authenticated HTTP implementation by default', () => {
    expect(reflectionsRepository).toBeInstanceOf(HttpReflectionsRepository);
  });
});

describe('fixtureReflectionsRepository', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('serves the complete hardcoded fixture for every range without calling fetch', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValue(new Error('The reflections API must not be called'));

    const allResult = await fixtureReflectionsRepository.getReflection({
      range: 'all',
    });
    const sevenDayResult = await fixtureReflectionsRepository.getReflection({
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
    const initial = await fixtureReflectionsRepository.getReflection({
      range: '30d',
    });
    const insight = initial.data.hiddenDriver;

    expect(initial.snapshot).not.toBeNull();
    expect(insight.status).toBe('available');
    if (!initial.snapshot || insight.status !== 'available') return;

    await fixtureReflectionsRepository.putFeedback({
      snapshotId: initial.snapshot.id,
      insightId: insight.id,
      response: 'resonates',
    });
    const refreshed = await fixtureReflectionsRepository.getReflection({
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

  it('posts no body to the exact recalculation endpoint and strictly parses 202', async () => {
    const result = {
      status: 'accepted' as const,
      jobId: '10000000-0000-4000-8000-000000000099',
    };
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(result, { status: 202 }));
    const repository = new HttpReflectionsRepository(request);

    await expect(repository.recalculate()).resolves.toEqual(result);
    expect(request).toHaveBeenCalledWith('/api/v1/reflections/recalculate', {
      method: 'POST',
      signal: undefined,
    });
    expect(request.mock.calls[0]?.[1]).not.toHaveProperty('body');
    expect(request.mock.calls[0]?.[1]).not.toHaveProperty('headers');
  });

  it.each([
    [409, 'REFLECTION_ALREADY_CURRENT'],
    [409, 'REFLECTION_NOT_ELIGIBLE'],
    [503, 'REFLECTION_RECALCULATION_UNAVAILABLE'],
  ] as const)(
    'preserves recalculation status %s and error code %s',
    async (status, errorCode) => {
      const request = vi.fn<typeof fetch>().mockResolvedValue(
        Response.json(
          {
            error_code: errorCode,
            message: 'Safe public message.',
          },
          { status },
        ),
      );
      const repository = new HttpReflectionsRepository(request);

      await expect(repository.recalculate()).rejects.toEqual(
        new ReflectionRequestError(
          `Reflection recalculation request failed: ${status}`,
          status,
          errorCode,
        ),
      );
    },
  );

  it('forwards abort signals to cached reads and recalculation', async () => {
    const controller = new AbortController();
    const request = vi.fn<typeof fetch>().mockImplementation((_path, init) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'));
        });
      });
    });
    const repository = new HttpReflectionsRepository(request);
    const read = repository.getReflection({ range: 'all' }, controller.signal);

    controller.abort();
    await expect(read).rejects.toMatchObject({ name: 'AbortError' });

    const recalculationController = new AbortController();
    const recalculate = repository.recalculate(recalculationController.signal);
    recalculationController.abort();
    await expect(recalculate).rejects.toMatchObject({ name: 'AbortError' });
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
      'Reflection feedback request failed: 404',
    );
    await expect(repository.putFeedback(feedbackInput)).rejects.toThrow();
  });

  it('rejects malformed accepted recalculation responses', async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json({ status: 'accepted' }, { status: 202 }),
      );
    const repository = new HttpReflectionsRepository(request);

    await expect(repository.recalculate()).rejects.toThrow();
  });

  it('rejects a valid recalculation body returned with a non-202 success status', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({
        status: 'accepted',
        jobId: '10000000-0000-4000-8000-000000000099',
      }),
    );
    const repository = new HttpReflectionsRepository(request);

    await expect(repository.recalculate()).rejects.toThrow(
      'Reflection recalculation request returned unexpected status: 200',
    );
  });
});

import { describe, expect, it, vi } from 'vitest';

import { journeyStatusFixture, journeyStreamForRange } from './fixtures';
import { HttpJourneyRepository } from './repository';

describe('HttpJourneyRepository', () => {
  it('sends range and user id to the Journey endpoint', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          entries: [],
          range: '6m',
          stream: journeyStreamForRange('6m'),
          totalAvailable: 0,
        }),
      ),
    );
    const repository = new HttpJourneyRepository(request);

    await repository.getJourney('6m', 'reader id');

    expect(request).toHaveBeenCalledWith(
      '/api/v1/journey?range=6m&userId=reader+id',
    );
  });

  it('loads status for the authenticated user and rejects failed responses', async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify(journeyStatusFixture)))
      .mockResolvedValueOnce(new Response(null, { status: 403 }));
    const repository = new HttpJourneyRepository(request);

    await expect(repository.getJourneyStatus('reader-id')).resolves.toEqual(
      journeyStatusFixture,
    );
    await expect(repository.getJourneyStatus('another-id')).rejects.toThrow(
      'Journey request failed: 403',
    );
  });
});

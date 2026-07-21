import { describe, expect, it } from 'vitest';

import { JOURNEY_RANGES } from './constants';
import { journeyEntryFixtures, MockJourneyRepository } from './mock-repository';

describe('MockJourneyRepository', () => {
  it('returns the requested number of monthly buckets for bounded ranges', async () => {
    const repository = new MockJourneyRepository(journeyEntryFixtures, 0);

    await expect(
      repository.getJourney('6m', 'reader-id'),
    ).resolves.toMatchObject({
      entries: expect.arrayContaining([expect.any(Object)]),
    });
    expect(
      (await repository.getJourney('6m', 'reader-id')).entries,
    ).toHaveLength(6);
    expect(
      (await repository.getJourney('1y', 'reader-id')).entries,
    ).toHaveLength(12);
  });

  it('returns identical fixed Journey data for every user and range', async () => {
    const repository = new MockJourneyRepository(journeyEntryFixtures, 0);

    await expect(repository.getJourneyStatus('first-user')).resolves.toEqual(
      await repository.getJourneyStatus('second-user'),
    );

    for (const range of JOURNEY_RANGES) {
      await expect(repository.getJourney(range, 'first-user')).resolves.toEqual(
        await repository.getJourney(range, 'second-user'),
      );
    }
  });
});

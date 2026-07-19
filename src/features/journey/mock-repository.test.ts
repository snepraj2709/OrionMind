import { describe, expect, it } from 'vitest';

import { journeyEntryFixtures, MockJourneyRepository } from './mock-repository';

describe('MockJourneyRepository', () => {
  it('returns the requested number of monthly buckets for bounded ranges', async () => {
    const repository = new MockJourneyRepository(journeyEntryFixtures, 0);

    await expect(repository.getJourneyEntries('6m')).resolves.toMatchObject({
      entries: expect.arrayContaining([expect.any(Object)]),
    });
    expect((await repository.getJourneyEntries('6m')).entries).toHaveLength(6);
    expect((await repository.getJourneyEntries('1y')).entries).toHaveLength(12);
  });
});

import { simulateLatency } from '@/services/mock-delay';

import {
  cloneJourneyEntries,
  journeyEntriesForRange,
  journeyEntryFixtures,
  journeyStatusFixture,
  journeyStreamForRange,
} from './fixtures';
import type {
  JourneyEntry,
  JourneyRange,
  JourneyResponse,
  JourneyStatusResponse,
} from './model';
import type { JourneyJournalService, JourneyRepository } from './repository';

export { journeyEntryFixtures } from './fixtures';

export class MockJourneyJournalService implements JourneyJournalService {
  constructor(
    private readonly entries: JourneyEntry[] = journeyEntryFixtures,
    private readonly delay = 280,
  ) {}

  async getJournalEntries(): Promise<JourneyEntry[]> {
    await simulateLatency(this.delay);
    return cloneJourneyEntries(this.entries);
  }
}

export class MockJourneyRepository implements JourneyRepository {
  private readonly service: JourneyJournalService;

  constructor(
    entries: JourneyEntry[] = journeyEntryFixtures,
    delay = 280,
    private readonly status: JourneyStatusResponse = journeyStatusFixture,
  ) {
    this.service = new MockJourneyJournalService(entries, delay);
  }

  async getJourney(
    range: JourneyRange,
    userId: string,
  ): Promise<JourneyResponse> {
    void userId;
    const entries = await this.service.getJournalEntries();
    return {
      entries: journeyEntriesForRange(entries, range),
      range,
      stream: journeyStreamForRange(range),
      totalAvailable: entries.length,
    };
  }

  async getJourneyStatus(userId: string): Promise<JourneyStatusResponse> {
    void userId;
    await simulateLatency(0);
    return { ...this.status };
  }
}

import { simulateLatency } from '@/services/mock-delay';

import type {
  JournalEntry,
  ReflectionEntriesResult,
  ReflectionRange,
} from './model';
import { reflectionEntryFixtures } from './fixtures';
import type {
  ReflectionJournalService,
  ReflectionsRepository,
} from './repository';

export { reflectionEntryFixtures } from './fixtures';

function cloneEntries(entries: JournalEntry[]) {
  return entries.map((entry) => ({
    entry_date: entry.entry_date,
    content: {
      added_energy: [...entry.content.added_energy],
      drained_energy: [...entry.content.drained_energy],
      self_knowledge: [...entry.content.self_knowledge],
    },
  }));
}

function entriesForRange(entries: JournalEntry[], range: ReflectionRange) {
  if (range === 'all' || entries.length === 0) return entries;

  const latestDate = entries.reduce(
    (latest, entry) => (entry.entry_date > latest ? entry.entry_date : latest),
    entries[0]!.entry_date,
  );
  const finalDay = new Date(`${latestDate}T00:00:00Z`);
  const periodDays = range === '7d' ? 7 : 30;
  const firstDay = new Date(finalDay);
  firstDay.setUTCDate(firstDay.getUTCDate() - (periodDays - 1));
  const firstDate = firstDay.toISOString().slice(0, 10);

  return entries.filter((entry) => entry.entry_date >= firstDate);
}

export class MockReflectionJournalService implements ReflectionJournalService {
  constructor(
    private readonly entries: JournalEntry[] = reflectionEntryFixtures,
    private readonly delay = 260,
  ) {}

  async getJournalEntries(): Promise<JournalEntry[]> {
    await simulateLatency(this.delay);
    return cloneEntries(this.entries);
  }
}

export class MockReflectionsRepository implements ReflectionsRepository {
  private readonly service: ReflectionJournalService;

  constructor(entries: JournalEntry[] = reflectionEntryFixtures, delay = 260) {
    this.service = new MockReflectionJournalService(entries, delay);
  }

  async getReflectionEntries(
    range: ReflectionRange,
  ): Promise<ReflectionEntriesResult> {
    const entries = await this.service.getJournalEntries();
    return {
      entries: entriesForRange(entries, range),
      totalAvailable: entries.length,
    };
  }
}

export const reflectionsRepository = new MockReflectionsRepository();

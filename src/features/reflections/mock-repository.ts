import { simulateLatency } from '@/services/mock-delay';
import { mockOrionStore } from '@/services/mock-orion-store';
import type { ApprovedReflectionEvidence } from '@/types/records';

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

interface ReflectionEvidenceSource {
  listApprovedReflectionEvidence(): ApprovedReflectionEvidence[];
}

function mergeApprovedEvidence(
  entries: JournalEntry[],
  evidence: ApprovedReflectionEvidence[],
) {
  const merged = cloneEntries(entries);

  evidence.forEach((item) => {
    const existing = merged.find(
      (entry) => entry.entry_date === item.entryDate,
    );
    if (existing) {
      if (!existing.content.self_knowledge.includes(item.content)) {
        existing.content.self_knowledge.push(item.content);
      }
      return;
    }

    merged.push({
      entry_date: item.entryDate,
      content: {
        added_energy: [],
        drained_energy: [],
        self_knowledge: [item.content],
      },
    });
  });

  return merged.sort((left, right) =>
    left.entry_date.localeCompare(right.entry_date),
  );
}

export class MockReflectionJournalService implements ReflectionJournalService {
  constructor(
    private readonly entries: JournalEntry[] = reflectionEntryFixtures,
    private readonly delay = 260,
    private readonly evidenceSource?: ReflectionEvidenceSource,
  ) {}

  async getJournalEntries(): Promise<JournalEntry[]> {
    await simulateLatency(this.delay);
    return mergeApprovedEvidence(
      this.entries,
      this.evidenceSource?.listApprovedReflectionEvidence() ?? [],
    );
  }
}

export class MockReflectionsRepository implements ReflectionsRepository {
  private readonly service: ReflectionJournalService;

  constructor(
    entries: JournalEntry[] = reflectionEntryFixtures,
    delay = 260,
    evidenceSource?: ReflectionEvidenceSource,
  ) {
    this.service = new MockReflectionJournalService(
      entries,
      delay,
      evidenceSource,
    );
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

export const reflectionsRepository = new MockReflectionsRepository(
  reflectionEntryFixtures,
  260,
  mockOrionStore,
);

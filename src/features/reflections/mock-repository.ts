import { simulateLatency } from '@/services/mock-delay';
import type { ApprovedReflectionEvidence } from '@/types/records';

import type { ReflectionApiResponse, ReflectionRequest } from './api-schema';
import { reflectionEntryFixtures } from './fixtures';
import type { JournalEntry } from './model';
import { buildReflectionApiResponse } from './response-builder';
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

  async getReflection(
    input: ReflectionRequest,
  ): Promise<ReflectionApiResponse> {
    const entries = await this.service.getJournalEntries();
    return buildReflectionApiResponse({
      ...input,
      entries,
      totalAvailable: entries.length,
    });
  }
}

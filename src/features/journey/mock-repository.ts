import type {
  EntryTheme,
  JourneyEntriesResult,
  JourneyEntry,
  JourneyRange,
} from './model';
import type { JourneyJournalService, JourneyRepository } from './repository';

const themeCycles: EntryTheme[][] = [
  [
    { rank: 'primary', value: 'career' },
    { rank: 'secondary', value: 'personal_growth' },
    { rank: 'tertiary', value: 'money' },
  ],
  [
    { rank: 'primary', value: 'personal_growth' },
    { rank: 'secondary', value: 'career' },
    { rank: 'tertiary', value: 'health' },
  ],
  [
    { rank: 'primary', value: 'love_life' },
    { rank: 'secondary', value: 'home_lifestyle' },
    { rank: 'tertiary', value: 'family_friends' },
  ],
  [
    { rank: 'primary', value: 'health' },
    { rank: 'secondary', value: 'personal_growth' },
    { rank: 'tertiary', value: 'fun_recreation' },
  ],
];

export const journeyEntryFixtures: JourneyEntry[] = Array.from(
  { length: 30 },
  (_, index) => {
    const date = new Date(Date.UTC(2023, 8 + index, 5));
    return {
      entry_date: date.toISOString().slice(0, 10),
      theme: themeCycles[Math.floor(index / 8) % themeCycles.length]!,
      content: {
        added_energy: [
          `A small step during month ${index + 1} made the direction feel more visible.`,
        ],
        drained_energy: [
          `Competing responsibilities during month ${index + 1} reduced the space available to recover.`,
        ],
        self_knowledge: [
          `I was beginning to understand what I wanted to carry forward from month ${index + 1}.`,
        ],
      },
    };
  },
);

function wait(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function cloneEntries(entries: JourneyEntry[]) {
  return entries.map((entry) => ({
    entry_date: entry.entry_date,
    theme: entry.theme.map((theme) => ({ ...theme })),
    content: {
      added_energy: [...entry.content.added_energy],
      drained_energy: [...entry.content.drained_energy],
      self_knowledge: [...entry.content.self_knowledge],
    },
  }));
}

function entriesForRange(entries: JourneyEntry[], range: JourneyRange) {
  if (range === 'all' || entries.length === 0) return entries;

  const periodMonths: Record<Exclude<JourneyRange, 'all'>, number> = {
    '6m': 6,
    '1y': 12,
    '2y': 24,
    '3y': 36,
    '5y': 60,
  };
  const finalDate = new Date(`${entries.at(-1)!.entry_date}T00:00:00Z`);
  finalDate.setUTCMonth(finalDate.getUTCMonth() - periodMonths[range]);
  const firstDate = finalDate.toISOString().slice(0, 10);
  return entries.filter((entry) => entry.entry_date >= firstDate);
}

export class MockJourneyJournalService implements JourneyJournalService {
  constructor(
    private readonly entries: JourneyEntry[] = journeyEntryFixtures,
    private readonly delay = 280,
  ) {}

  async getJournalEntries(): Promise<JourneyEntry[]> {
    await wait(this.delay);
    return cloneEntries(this.entries);
  }
}

export class MockJourneyRepository implements JourneyRepository {
  private readonly service: JourneyJournalService;

  constructor(entries: JourneyEntry[] = journeyEntryFixtures, delay = 280) {
    this.service = new MockJourneyJournalService(entries, delay);
  }

  async getJourneyEntries(range: JourneyRange): Promise<JourneyEntriesResult> {
    const entries = await this.service.getJournalEntries();
    return {
      entries: entriesForRange(entries, range),
      totalAvailable: entries.length,
    };
  }
}

export const journeyRepository = new MockJourneyRepository();

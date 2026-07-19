import type {
  JournalEntry,
  ReflectionEntriesResult,
  ReflectionRange,
} from './model';
import type {
  ReflectionJournalService,
  ReflectionsRepository,
} from './repository';

const dates = [
  '2025-04-14',
  '2025-04-15',
  '2025-04-16',
  '2025-04-17',
  '2025-04-18',
  '2025-04-19',
  '2025-04-20',
  '2025-04-21',
  '2025-04-22',
  '2025-04-23',
  '2025-04-24',
  '2025-04-25',
  '2025-04-26',
  '2025-04-27',
  '2025-04-28',
  '2025-04-29',
  '2025-04-30',
  '2025-05-01',
  '2025-05-02',
  '2025-05-04',
  '2025-05-06',
  '2025-05-07',
  '2025-05-08',
];

const entryPatterns: JournalEntry['content'][] = [
  {
    added_energy: [
      'Explaining a difficult idea to someone else made the whole subject click for me.',
    ],
    drained_energy: [
      'I kept opening new directions before finishing the one in front of me.',
    ],
    self_knowledge: [
      'I feel most capable when curiosity becomes something I can make or share.',
    ],
  },
  {
    added_energy: [
      'The open afternoon gave me room to follow one question all the way through.',
    ],
    drained_energy: [
      'By evening I was measuring progress against every idea I had not chosen.',
    ],
    self_knowledge: [
      'Autonomy matters, but I still want visible proof that my effort is becoming real.',
    ],
  },
  {
    added_energy: [
      'A long run and an hour of painting left me feeling alert and fully present.',
    ],
    drained_energy: [
      'Pushing through poor sleep made even simple decisions feel heavy.',
    ],
    self_knowledge: [
      'Intensity gives me momentum, but consistency is what keeps me able to continue.',
    ],
  },
  {
    added_energy: [
      'A thoughtful conversation made me feel seen without needing to perform.',
    ],
    drained_energy: [
      'Trying to fit the group expectation made me feel less like myself.',
    ],
    self_knowledge: [
      'Recognition only restores me when it comes from people and work I respect.',
    ],
  },
  {
    added_energy: [
      'Turning a loose thought into a small working sketch gave the day a clear shape.',
    ],
    drained_energy: [
      'I searched for more inspiration when the current project became uncertain.',
    ],
    self_knowledge: [
      'Possibility feels safe because choosing one direction makes failure more visible.',
    ],
  },
];

export const reflectionEntryFixtures: JournalEntry[] = dates.map(
  (entry_date, index) => ({
    entry_date,
    content: entryPatterns[index % entryPatterns.length]!,
  }),
);

function wait(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

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
    await wait(this.delay);
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

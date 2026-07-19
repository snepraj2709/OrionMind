import type {
  ApprovalStatus,
  CreateTextEntryInput,
  EntryDetail,
  EntriesQuery,
  EntriesResult,
  EntrySummary,
  ExtractedItemKind,
} from './model';
import type { EntriesRepository } from './repository';

const entriesFixture: EntryDetail[] = [
  {
    id: 'e1',
    date: '2025-07-10',
    inputType: 'text',
    status: 'completed',
    content:
      'This morning I sat with my coffee longer than usual, watching the light change across the kitchen wall. There was something in that stillness — a kind of permission to exist without producing anything.',
    themes: ['personalGrowth', 'health', 'familyAndFriends'],
    ideas: [
      {
        id: 'i1',
        content:
          'I want to establish a morning ritual centered on slow, screen-free time before engaging with the day.',
        kind: 'idea',
        status: 'pending_approval',
      },
    ],
    memories: [],
  },
  {
    id: 'e2',
    date: '2025-07-09',
    inputType: 'voice',
    status: 'completed',
    content:
      'I had a difficult conversation with my manager about the project direction. I went in feeling uncertain and came out feeling heard, which surprised me.',
    themes: ['career', 'personalGrowth', 'familyAndFriends'],
    ideas: [
      {
        id: 'i2',
        content:
          'I should practice stating my technical judgments clearly and early in meetings, rather than over-qualifying everything.',
        kind: 'idea',
        status: 'pending_approval',
      },
    ],
    memories: [
      {
        id: 'm1',
        content:
          'I found words in a work meeting that changed how I understand my own authority in technical conversations.',
        kind: 'memory',
        status: 'pending_approval',
      },
    ],
  },
  {
    id: 'e3',
    date: '2025-07-08',
    inputType: 'text',
    status: 'completed',
    content:
      'I finally finished the painting I started three weeks ago. Finishing it taught me more than the canvases that came out beautifully ever could.',
    themes: ['funAndRecreation', 'personalGrowth', 'health'],
    ideas: [],
    memories: [
      {
        id: 'm2',
        content:
          'I completed a painting I was unsatisfied with, and discovered it taught me more than my successful works have.',
        kind: 'memory',
        status: 'approved',
      },
    ],
  },
  {
    id: 'e4',
    date: '2025-07-07',
    inputType: 'text',
    status: 'processing',
    content:
      'Went for a long walk along the canal. I did not bring headphones. I just walked and let thoughts come and go without chasing any of them.',
    themes: [],
    ideas: [],
    memories: [],
  },
  {
    id: 'e5',
    date: '2025-07-04',
    inputType: 'voice',
    status: 'failed',
    content:
      'Woke up early. The apartment was very quiet. Made tea and sat on the floor, reading old journal entries from two years ago.',
    themes: [],
    ideas: [],
    memories: [],
    processingError:
      'Orion could not complete this reflection. Your original entry is safe.',
  },
];

function wait(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export class MockEntriesRepository implements EntriesRepository {
  constructor(
    private readonly entries: EntryDetail[] = entriesFixture,
    private readonly delay = 240,
  ) {}

  async listEntries(query: EntriesQuery): Promise<EntriesResult> {
    await wait(this.delay);

    const normalizedSearch = query.search.trim().toLocaleLowerCase();
    const matching = this.entries.filter((entry) => {
      const matchesSearch =
        normalizedSearch.length === 0 ||
        entry.content.toLocaleLowerCase().includes(normalizedSearch);
      const matchesStatus =
        query.status === 'all' || entry.status === query.status;

      return matchesSearch && matchesStatus;
    });
    const start = query.pageIndex * query.pageSize;

    return {
      items: matching.slice(start, start + query.pageSize),
      total: matching.length,
      totalAll: this.entries.length,
    };
  }

  async getEntry(entryId: string): Promise<EntryDetail | null> {
    await wait(this.delay);
    return this.entries.find((entry) => entry.id === entryId) ?? null;
  }

  async createTextEntry(input: CreateTextEntryInput): Promise<EntrySummary> {
    await wait(this.delay);

    const entry: EntryDetail = {
      id: `entry-${Date.now()}`,
      content: input.content,
      date: new Date().toISOString().slice(0, 10),
      inputType: 'text',
      status: 'processing',
      themes: [],
      ideas: [],
      memories: [],
    };
    this.entries.unshift(entry);
    return entry;
  }

  async createVoiceEntry(recording: Blob): Promise<EntrySummary> {
    await wait(this.delay);
    if (recording.size === 0) throw new Error('The recording is empty.');

    const entry: EntryDetail = {
      id: `entry-${Date.now()}`,
      content:
        'Your voice entry is being transcribed. Its text will appear here when processing is complete.',
      date: new Date().toISOString().slice(0, 10),
      inputType: 'voice',
      status: 'processing',
      themes: [],
      ideas: [],
      memories: [],
    };
    this.entries.unshift(entry);
    return entry;
  }

  async decideExtractedItem(input: {
    entryId: string;
    itemId: string;
    kind: ExtractedItemKind;
    status: Exclude<ApprovalStatus, 'pending_approval'>;
  }): Promise<EntryDetail> {
    await wait(this.delay);

    const entry = this.entries.find(
      (candidate) => candidate.id === input.entryId,
    );
    if (!entry) throw new Error('Entry not found.');

    const collection = input.kind === 'idea' ? entry.ideas : entry.memories;
    const item = collection.find((candidate) => candidate.id === input.itemId);
    if (!item) throw new Error('Extracted item not found.');
    if (item.status !== 'pending_approval') {
      throw new Error('This item has already been reviewed.');
    }

    item.status = input.status;
    return entry;
  }

  async retryEntry(entryId: string): Promise<EntryDetail> {
    await wait(this.delay);
    const entry = this.entries.find((candidate) => candidate.id === entryId);
    if (!entry) throw new Error('Entry not found.');

    entry.status = 'processing';
    delete entry.processingError;
    return entry;
  }
}

export const entriesRepository: EntriesRepository = new MockEntriesRepository();

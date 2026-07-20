import type { ApprovalStatus, ExtractedItemKind } from '@/config/status';
import type {
  ApprovedReflectionEvidence,
  ApprovalRecord,
  EntryDetail,
  SavedItemRecord,
} from '@/types/records';

const entryFixtures: EntryDetail[] = [
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
    reflections: [
      {
        id: 'r1',
        content:
          'Slow, unstructured mornings help me hear what I need before the day starts asking things of me.',
        kind: 'reflection',
        status: 'pending_approval',
      },
    ],
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
    reflections: [
      {
        id: 'r2',
        content:
          'I trust my judgment more when I state it plainly and let the conversation respond.',
        kind: 'reflection',
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
    reflections: [
      {
        id: 'r3',
        content:
          'Finishing imperfect work teaches me more than protecting the possibility of perfect work.',
        kind: 'reflection',
        status: 'pending_approval',
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
    reflections: [],
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
    reflections: [],
    processingError:
      'Orion could not complete this reflection. Your original entry is safe.',
  },
];

const savedItemFixtures: SavedItemRecord[] = [
  {
    id: 'saved-idea-1',
    content:
      'I want to protect one screen-free morning each week and notice what changes.',
    entryDate: '2025-07-03',
    entryId: 'e1',
    kind: 'idea',
  },
  {
    id: 'saved-idea-2',
    content:
      'I should make creative work before evaluating whether it is useful.',
    entryDate: '2025-06-28',
    entryId: 'e3',
    kind: 'idea',
  },
  {
    id: 'saved-memory-1',
    content:
      'I completed a painting I was unsatisfied with, and discovered it taught me more than my successful works have.',
    entryDate: '2025-07-08',
    entryId: 'e3',
    kind: 'memory',
  },
  {
    id: 'saved-memory-2',
    content:
      'I found words in a work meeting that changed how I understand my own authority.',
    entryDate: '2025-06-21',
    entryId: 'e2',
    kind: 'memory',
  },
];

function cloneEntries(entries: EntryDetail[]) {
  return entries.map((entry) => ({
    ...entry,
    ideas: entry.ideas.map((item) => ({ ...item })),
    memories: entry.memories.map((item) => ({ ...item })),
    reflections: entry.reflections.map((item) => ({ ...item })),
    themes: [...entry.themes],
  }));
}

export class MockOrionStore {
  readonly entries: EntryDetail[];
  readonly savedItems: SavedItemRecord[];

  constructor(
    entries: EntryDetail[] = entryFixtures,
    savedItems: SavedItemRecord[] = savedItemFixtures,
  ) {
    this.entries = cloneEntries(entries);
    this.savedItems = savedItems.map((item) => ({ ...item }));
  }

  listPendingApprovals(): ApprovalRecord[] {
    return this.entries.flatMap((entry) =>
      [...entry.ideas, ...entry.memories, ...entry.reflections]
        .filter((item) => item.status === 'pending_approval')
        .map((item) => ({
          ...item,
          entryDate: entry.date,
          entryId: entry.id,
          themes: [...entry.themes],
        })),
    );
  }

  listApprovedReflectionEvidence(): ApprovedReflectionEvidence[] {
    return this.entries.flatMap((entry) =>
      entry.reflections
        .filter((item) => item.status === 'approved')
        .map((item) => ({
          content: item.content,
          entryDate: entry.date,
        })),
    );
  }

  decideExtractedItem(input: {
    entryId?: string;
    itemId: string;
    kind?: ExtractedItemKind;
    status: Exclude<ApprovalStatus, 'pending_approval'>;
  }): ApprovalRecord {
    const entry = this.entries.find(
      (candidate) =>
        (!input.entryId || candidate.id === input.entryId) &&
        [
          ...candidate.ideas,
          ...candidate.memories,
          ...candidate.reflections,
        ].some((item) => item.id === input.itemId),
    );
    if (!entry) throw new Error('The review item was not found.');

    const itemCollections = {
      idea: entry.ideas,
      memory: entry.memories,
      reflection: entry.reflections,
    } satisfies Record<ExtractedItemKind, typeof entry.ideas>;
    const items = input.kind
      ? itemCollections[input.kind]
      : [...entry.ideas, ...entry.memories, ...entry.reflections];
    const item = items.find((candidate) => candidate.id === input.itemId);
    if (!item) throw new Error('The review item was not found.');
    if (item.status !== 'pending_approval') {
      throw new Error('This item has already been reviewed.');
    }

    item.status = input.status;
    const record = {
      ...item,
      entryDate: entry.date,
      entryId: entry.id,
      themes: [...entry.themes],
    };
    if (
      input.status === 'approved' &&
      item.kind !== 'reflection' &&
      !this.savedItems.some((savedItem) => savedItem.id === item.id)
    ) {
      this.savedItems.unshift({
        id: item.id,
        content: item.content,
        entryDate: entry.date,
        entryId: entry.id,
        kind: item.kind,
      });
    }
    return record;
  }
}

export const mockOrionStore = new MockOrionStore();

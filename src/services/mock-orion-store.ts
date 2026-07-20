import type { ApprovalStatus, ExtractedItemKind } from '@/config/status';
import { entryDetailFixtures } from '@/features/entries/fixtures';
import type {
  ApprovedReflectionEvidence,
  ApprovalRecord,
  EntryDetail,
  SavedItemRecord,
} from '@/types/records';

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
    entries: EntryDetail[] = entryDetailFixtures,
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

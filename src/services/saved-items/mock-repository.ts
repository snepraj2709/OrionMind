import type {
  SavedItemRecord,
  SavedItemsQuery,
  SavedItemsRepository,
  SavedItemsResult,
} from './types';

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

function wait(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export class MockSavedItemsRepository implements SavedItemsRepository {
  private readonly items: SavedItemRecord[];

  constructor(
    items: SavedItemRecord[] = savedItemFixtures,
    private readonly delay = 220,
  ) {
    this.items = items.map((item) => ({ ...item }));
  }

  async listSavedItems(query: SavedItemsQuery): Promise<SavedItemsResult> {
    await wait(this.delay);
    const allForKind = this.items
      .filter((item) => item.kind === query.kind)
      .sort((left, right) => right.entryDate.localeCompare(left.entryDate));
    const normalizedSearch = query.search.trim().toLocaleLowerCase();
    const matching = allForKind.filter(
      (item) =>
        normalizedSearch.length === 0 ||
        item.content.toLocaleLowerCase().includes(normalizedSearch),
    );
    const start = query.pageIndex * query.pageSize;

    return {
      items: matching.slice(start, start + query.pageSize),
      total: matching.length,
      totalAll: allForKind.length,
    };
  }
}

export const savedItemsRepository = new MockSavedItemsRepository();

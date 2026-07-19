import { mockOrionStore } from '@/services/mock-orion-store';
import { simulateLatency } from '@/services/mock-delay';

import type {
  SavedItemRecord,
  SavedItemsQuery,
  SavedItemsRepository,
  SavedItemsResult,
} from './types';

export class MockSavedItemsRepository implements SavedItemsRepository {
  private readonly items: SavedItemRecord[];

  constructor(
    items: SavedItemRecord[] = mockOrionStore.savedItems,
    private readonly delay = 220,
  ) {
    this.items =
      items === mockOrionStore.savedItems
        ? mockOrionStore.savedItems
        : items.map((item) => ({ ...item }));
  }

  async listSavedItems(query: SavedItemsQuery): Promise<SavedItemsResult> {
    await simulateLatency(this.delay);
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

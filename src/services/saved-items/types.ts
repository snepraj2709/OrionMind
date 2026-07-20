import type { SavedItemKind, SavedItemRecord } from '@/types/records';

export type { SavedItemKind, SavedItemRecord } from '@/types/records';

export interface SavedItemsQuery {
  kind: SavedItemKind;
  pageIndex: number;
  pageSize: number;
  search: string;
}

export interface SavedItemsResult {
  items: SavedItemRecord[];
  total: number;
  totalAll: number;
}

export interface SavedItemsRepository {
  listSavedItems(query: SavedItemsQuery): Promise<SavedItemsResult>;
}

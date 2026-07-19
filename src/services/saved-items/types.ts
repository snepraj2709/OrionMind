import type { ExtractedItemKind } from '@/config/status';
import type { SavedItemRecord } from '@/types/records';

export type SavedItemKind = ExtractedItemKind;
export type { SavedItemRecord } from '@/types/records';

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

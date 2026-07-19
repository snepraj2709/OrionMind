export type SavedItemKind = 'idea' | 'memory';

export interface SavedItemRecord {
  id: string;
  content: string;
  entryId: string;
  entryDate: string;
  kind: SavedItemKind;
}

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

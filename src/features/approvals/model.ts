import type { ApprovalStatus, ExtractedItemKind } from '@/features/entries';

export type ApprovalKindFilter = 'all' | ExtractedItemKind;

export interface ApprovalRecord {
  id: string;
  content: string;
  kind: ExtractedItemKind;
  status: ApprovalStatus;
  entryId: string;
  entryDate: string;
}

export interface ApprovalsQuery {
  kind: ApprovalKindFilter;
  search: string;
  pageIndex: number;
  pageSize: number;
}

export interface ApprovalsResult {
  items: ApprovalRecord[];
  total: number;
  totalAll: number;
}

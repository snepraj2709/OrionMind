import type { ExtractedItemKind } from '@/config/status';
import type { ApprovalRecord } from '@/types/records';

export type { ApprovalRecord } from '@/types/records';

export type ApprovalKindFilter = 'all' | ExtractedItemKind;

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

import type { ExtractedItemKind } from '@/config/status';
import type { ThemeKey } from '@/config/design-system';
import type { ApprovalRecord } from '@/types/records';

export type { ApprovalRecord } from '@/types/records';

export type ApprovalKindFilter = 'all' | ExtractedItemKind;
export type ApprovalStatusFilter = 'all' | 'pending_approval';
export type ApprovalThemeFilter = 'all' | ThemeKey;

export interface ApprovalsQuery {
  kind: ApprovalKindFilter;
  status: ApprovalStatusFilter;
  theme: ApprovalThemeFilter;
  search: string;
  pageIndex: number;
  pageSize: number;
}

export interface ApprovalsResult {
  items: ApprovalRecord[];
  total: number;
  totalAll: number;
}

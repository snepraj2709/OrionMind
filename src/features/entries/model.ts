import type { EntryStatus } from '@/config/status';
import type { EntrySummary } from '@/types/records';

export type {
  ApprovalStatus,
  EntryStatus,
  ExtractedItemKind,
} from '@/config/status';
export type { EntryDetail, EntrySummary, ExtractedItem } from '@/types/records';
export type EntryInputType = 'text' | 'voice';
export type EntryStatusFilter = 'all' | EntryStatus;

export interface EntriesQuery {
  search: string;
  status: EntryStatusFilter;
  pageIndex: number;
  pageSize: number;
}

export interface EntriesResult {
  items: EntrySummary[];
  total: number;
  totalAll: number;
}

export interface CreateTextEntryInput {
  content: string;
}

import type { ThemeKey } from '@/config/design-system';

export type EntryStatus = 'processing' | 'completed' | 'failed';
export type EntryInputType = 'text' | 'voice';
export type EntryStatusFilter = 'all' | EntryStatus;
export type ApprovalStatus = 'pending_approval' | 'approved' | 'rejected';
export type ExtractedItemKind = 'idea' | 'memory';

export interface ExtractedItem {
  id: string;
  content: string;
  kind: ExtractedItemKind;
  status: ApprovalStatus;
}

export interface EntrySummary {
  id: string;
  content: string;
  date: string;
  status: EntryStatus;
  inputType: EntryInputType;
  themes: ThemeKey[];
}

export interface EntryDetail extends EntrySummary {
  ideas: ExtractedItem[];
  memories: ExtractedItem[];
  processingError?: string;
}

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

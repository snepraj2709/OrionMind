import type { EntrySummary } from '@/types/records';

export type {
  ApprovalStatus,
  EntryStatus,
  ExtractedItemKind,
} from '@/config/status';
export type { EntryDetail, EntrySummary, ExtractedItem } from '@/types/records';
export type EntryInputType = 'text' | 'voice';

export interface EntriesQuery {
  pageIndex: number;
  pageSize: number;
}

export interface EntriesResult {
  items: EntrySummary[];
  total: number;
  page: number;
  pageSize: number;
}

export interface CreateTextEntryInput {
  content: string;
}

export interface CreateVoiceEntryInput {
  idempotencyKey: string;
  recording: Blob;
}

export interface EntryDraft {
  content: string | null;
  updatedAt: string | null;
}

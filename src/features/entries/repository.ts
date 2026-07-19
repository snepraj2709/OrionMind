import type {
  ApprovalStatus,
  CreateTextEntryInput,
  EntryDetail,
  EntriesQuery,
  EntriesResult,
  EntrySummary,
  ExtractedItemKind,
} from './model';

export interface EntriesRepository {
  listEntries(query: EntriesQuery): Promise<EntriesResult>;
  getEntry(entryId: string): Promise<EntryDetail | null>;
  createTextEntry(input: CreateTextEntryInput): Promise<EntrySummary>;
  createVoiceEntry(recording: Blob): Promise<EntrySummary>;
  decideExtractedItem(input: {
    entryId: string;
    itemId: string;
    kind: ExtractedItemKind;
    status: Exclude<ApprovalStatus, 'pending_approval'>;
  }): Promise<EntryDetail>;
  retryEntry(entryId: string): Promise<EntryDetail>;
}

import { apiRequest, type ApiRequest } from '@/services/api-client';

import { mapEntriesApiItem } from './adapter';
import { entriesApiResponseSchema } from './api-schema';
import type {
  ApprovalStatus,
  CreateTextEntryInput,
  EntryDetail,
  EntriesQuery,
  EntriesResult,
  EntrySummary,
  ExtractedItemKind,
} from './model';

export interface CreateEntryInput {
  mode: 'text' | 'voice';
  content?: string;
  voice?: Blob;
}

export interface ExtractedItemDecisionInput {
  entryId: string;
  itemId: string;
  kind: ExtractedItemKind;
  status: Exclude<ApprovalStatus, 'pending_approval'>;
}

export interface EntriesListRepository {
  listEntries(query: EntriesQuery): Promise<EntriesResult>;
}

export interface EntriesRepository extends EntriesListRepository {
  getEntry(entryId: string): Promise<EntryDetail | null>;
  createTextEntry(input: CreateTextEntryInput): Promise<EntrySummary>;
  createVoiceEntry(recording: Blob): Promise<EntrySummary>;
  decideExtractedItem(input: ExtractedItemDecisionInput): Promise<EntryDetail>;
  retryEntry(entryId: string): Promise<EntryDetail>;
}

export class HttpEntriesRepository implements EntriesListRepository {
  constructor(private readonly request: ApiRequest = apiRequest) {}

  async listEntries(query: EntriesQuery): Promise<EntriesResult> {
    const params = new URLSearchParams({
      page: String(query.pageIndex + 1),
      page_size: String(query.pageSize),
    });
    const search = query.search.trim();
    if (search) params.set('search', search);
    if (query.status !== 'all') {
      params.set('processing_status', query.status);
    }

    const response = await this.request(`/api/v1/entries?${params}`);
    if (!response.ok) {
      throw new Error(`Entries request failed: ${response.status}`);
    }

    const body = entriesApiResponseSchema.parse(await response.json());

    return {
      items: body.items.map(mapEntriesApiItem),
      total: body.total,
      totalAll: body.total_all,
      page: body.page,
      pageSize: body.page_size,
    };
  }
}

export const entriesListRepository: EntriesListRepository =
  new HttpEntriesRepository();

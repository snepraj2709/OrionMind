import { apiRequest, type ApiRequest } from '@/services/api-client';

import { mapCreatedEntryApiResponse, mapEntriesApiItem } from './adapter';
import {
  createdEntryApiResponseSchema,
  entriesApiResponseSchema,
  entryDraftApiResponseSchema,
} from './api-schema';
import type {
  ApprovalStatus,
  CreateTextEntryInput,
  CreateVoiceEntryInput,
  EntryDraft,
  EntryDetail,
  EntriesQuery,
  EntriesResult,
  EntrySummary,
  ExtractedItemKind,
} from './model';

export interface CreateEntryInput {
  mode: 'text' | 'voice';
  content?: string;
  idempotencyKey?: string;
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

export interface EntryComposerRepository {
  getTextDraft(): Promise<EntryDraft>;
  saveTextDraft(content: string): Promise<EntryDraft>;
  discardTextDraft(): Promise<EntryDraft>;
  createTextEntry(input: CreateTextEntryInput): Promise<EntrySummary>;
  createVoiceEntry(input: CreateVoiceEntryInput): Promise<EntrySummary>;
}

export interface EntriesRepository
  extends EntriesListRepository, EntryComposerRepository {
  getEntry(entryId: string): Promise<EntryDetail | null>;
  decideExtractedItem(input: ExtractedItemDecisionInput): Promise<EntryDetail>;
  retryEntry(entryId: string): Promise<EntryDetail>;
}

export const MAX_VOICE_RECORDING_BYTES = 25 * 1024 * 1024;

const voiceFileExtensions: Record<string, string> = {
  'audio/wav': 'wav',
  'audio/x-wav': 'wav',
  'audio/mpeg': 'mp3',
  'audio/mp4': 'm4a',
  'audio/x-m4a': 'm4a',
  'audio/webm': 'webm',
  'audio/ogg': 'ogg',
};

export class EntryRequestError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'EntryRequestError';
  }
}

function draftFromResponse(response: unknown): EntryDraft {
  const draft = entryDraftApiResponseSchema.parse(response);
  return { content: draft.content, updatedAt: draft.updated_at };
}

async function requireOk(response: Response, operation: string) {
  if (!response.ok) {
    throw new EntryRequestError(
      `${operation} request failed: ${response.status}`,
      response.status,
    );
  }
  return response;
}

function voiceUpload(recording: Blob) {
  if (recording.size === 0) {
    throw new EntryRequestError('The recording is empty.');
  }
  if (recording.size > MAX_VOICE_RECORDING_BYTES) {
    throw new EntryRequestError('The recording exceeds the 25 MB limit.', 413);
  }
  const mimeType = recording.type.split(';', 1)[0]?.trim().toLowerCase();
  const extension = mimeType ? voiceFileExtensions[mimeType] : undefined;
  if (!mimeType || !extension) {
    throw new EntryRequestError('The recording format is unsupported.', 415);
  }
  return {
    blob: new Blob([recording], { type: mimeType }),
    filename: `orion-entry.${extension}`,
  };
}

export class HttpEntriesRepository
  implements EntriesListRepository, EntryComposerRepository
{
  constructor(private readonly request: ApiRequest = apiRequest) {}

  async listEntries(query: EntriesQuery): Promise<EntriesResult> {
    const params = new URLSearchParams({
      page: String(query.pageIndex + 1),
      page_size: String(query.pageSize),
    });

    const response = await this.request(`/api/v1/entries?${params}`);
    if (!response.ok) {
      throw new Error(`Entries request failed: ${response.status}`);
    }

    const body = entriesApiResponseSchema.parse(await response.json());

    return {
      items: body.items.map(mapEntriesApiItem),
      total: body.total,
      page: body.page,
      pageSize: body.page_size,
    };
  }

  async getTextDraft(): Promise<EntryDraft> {
    const response = await requireOk(
      await this.request('/api/v1/entry/draft'),
      'Draft restore',
    );
    return draftFromResponse(await response.json());
  }

  async saveTextDraft(content: string): Promise<EntryDraft> {
    const response = await requireOk(
      await this.request('/api/v1/entry/draft', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      }),
      'Draft save',
    );
    return draftFromResponse(await response.json());
  }

  async discardTextDraft(): Promise<EntryDraft> {
    const response = await requireOk(
      await this.request('/api/v1/entry/draft', { method: 'DELETE' }),
      'Draft discard',
    );
    return draftFromResponse(await response.json());
  }

  async createTextEntry(input: CreateTextEntryInput): Promise<EntrySummary> {
    const response = await requireOk(
      await this.request('/api/v1/entry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: input.content }),
      }),
      'Text entry',
    );
    return mapCreatedEntryApiResponse(
      createdEntryApiResponseSchema.parse(await response.json()),
    );
  }

  async createVoiceEntry(input: CreateVoiceEntryInput): Promise<EntrySummary> {
    const upload = voiceUpload(input.recording);
    const body = new FormData();
    body.append('audio', upload.blob, upload.filename);
    const response = await requireOk(
      await this.request('/api/v1/entries/voice', {
        method: 'POST',
        headers: { 'Idempotency-Key': input.idempotencyKey },
        body,
      }),
      'Voice entry',
    );
    return mapCreatedEntryApiResponse(
      createdEntryApiResponseSchema.parse(await response.json()),
    );
  }
}

const httpEntriesRepository = new HttpEntriesRepository();

export const entriesListRepository: EntriesListRepository =
  httpEntriesRepository;
export const entryComposerRepository: EntryComposerRepository =
  httpEntriesRepository;

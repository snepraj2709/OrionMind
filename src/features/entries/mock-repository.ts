import {
  mockOrionStore,
  type MockOrionStore,
} from '@/services/mock-orion-store';
import { simulateLatency } from '@/services/mock-delay';

import type {
  ApprovalStatus,
  CreateTextEntryInput,
  EntryDetail,
  EntriesQuery,
  EntriesResult,
  EntrySummary,
  ExtractedItemKind,
} from './model';
import type { EntriesRepository } from './repository';

export class MockEntriesRepository implements EntriesRepository {
  private readonly store: MockOrionStore | undefined;

  constructor(
    private readonly entries: EntryDetail[] = mockOrionStore.entries,
    private readonly delay = 240,
  ) {
    this.store =
      entries === mockOrionStore.entries ? mockOrionStore : undefined;
  }

  async listEntries(query: EntriesQuery): Promise<EntriesResult> {
    await simulateLatency(this.delay);
    const normalizedSearch = query.search.trim().toLocaleLowerCase();
    const matching = this.entries.filter((entry) => {
      const matchesSearch =
        normalizedSearch.length === 0 ||
        entry.content.toLocaleLowerCase().includes(normalizedSearch);
      const matchesStatus =
        query.status === 'all' || entry.status === query.status;
      return matchesSearch && matchesStatus;
    });
    const start = query.pageIndex * query.pageSize;

    return {
      items: matching.slice(start, start + query.pageSize),
      total: matching.length,
      totalAll: this.entries.length,
    };
  }

  async getEntry(entryId: string): Promise<EntryDetail | null> {
    await simulateLatency(this.delay);
    return this.entries.find((entry) => entry.id === entryId) ?? null;
  }

  async createTextEntry(input: CreateTextEntryInput): Promise<EntrySummary> {
    await simulateLatency(this.delay);
    const entry: EntryDetail = {
      id: `entry-${Date.now()}`,
      content: input.content,
      date: new Date().toISOString().slice(0, 10),
      inputType: 'text',
      status: 'processing',
      themes: [],
      ideas: [],
      memories: [],
    };
    this.entries.unshift(entry);
    return entry;
  }

  async createVoiceEntry(recording: Blob): Promise<EntrySummary> {
    await simulateLatency(this.delay);
    if (recording.size === 0) throw new Error('The recording is empty.');

    const entry: EntryDetail = {
      id: `entry-${Date.now()}`,
      content:
        'Your voice entry is being transcribed. Its text will appear here when processing is complete.',
      date: new Date().toISOString().slice(0, 10),
      inputType: 'voice',
      status: 'processing',
      themes: [],
      ideas: [],
      memories: [],
    };
    this.entries.unshift(entry);
    return entry;
  }

  async decideExtractedItem(input: {
    entryId: string;
    itemId: string;
    kind: ExtractedItemKind;
    status: Exclude<ApprovalStatus, 'pending_approval'>;
  }): Promise<EntryDetail> {
    await simulateLatency(this.delay);

    if (this.store) {
      this.store.decideExtractedItem(input);
      const storedEntry = this.entries.find(
        (candidate) => candidate.id === input.entryId,
      );
      if (!storedEntry) throw new Error('Entry not found.');
      return storedEntry;
    }

    const entry = this.entries.find(
      (candidate) => candidate.id === input.entryId,
    );
    if (!entry) throw new Error('Entry not found.');

    const collection = input.kind === 'idea' ? entry.ideas : entry.memories;
    const item = collection.find((candidate) => candidate.id === input.itemId);
    if (!item) throw new Error('Extracted item not found.');
    if (item.status !== 'pending_approval') {
      throw new Error('This item has already been reviewed.');
    }
    item.status = input.status;
    return entry;
  }

  async retryEntry(entryId: string): Promise<EntryDetail> {
    await simulateLatency(this.delay);
    const entry = this.entries.find((candidate) => candidate.id === entryId);
    if (!entry) throw new Error('Entry not found.');
    entry.status = 'processing';
    delete entry.processingError;
    return entry;
  }
}

export const entriesRepository: EntriesRepository = new MockEntriesRepository();

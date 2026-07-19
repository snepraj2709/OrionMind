import type {
  JournalEntry,
  ReflectionEntriesResult,
  ReflectionRange,
} from './model';

export interface ReflectionJournalService {
  getJournalEntries(): Promise<JournalEntry[]>;
}

export interface ReflectionsRepository {
  getReflectionEntries(
    range: ReflectionRange,
  ): Promise<ReflectionEntriesResult>;
}

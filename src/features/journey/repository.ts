import type { JourneyEntriesResult, JourneyEntry, JourneyRange } from './model';

export interface JourneyJournalService {
  getJournalEntries(): Promise<JourneyEntry[]>;
}

export interface JourneyRepository {
  getJourneyEntries(range: JourneyRange): Promise<JourneyEntriesResult>;
}

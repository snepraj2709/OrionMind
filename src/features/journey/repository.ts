import type {
  JourneyEntry,
  JourneyRange,
  JourneyResponse,
  JourneyStatusResponse,
} from './model';

export interface JourneyJournalService {
  getJournalEntries(): Promise<JourneyEntry[]>;
}

export interface JourneyRepository {
  getJourney(range: JourneyRange, userId: string): Promise<JourneyResponse>;
  getJourneyStatus(userId: string): Promise<JourneyStatusResponse>;
}

export class HttpJourneyRepository implements JourneyRepository {
  constructor(
    private readonly request: typeof fetch = (input, init) =>
      fetch(input, init),
  ) {}

  private async getJson<T>(path: string): Promise<T> {
    const response = await this.request(path);
    if (!response.ok)
      throw new Error(`Journey request failed: ${response.status}`);
    return response.json() as Promise<T>;
  }

  getJourney(range: JourneyRange, userId: string) {
    const params = new URLSearchParams({ range, userId });
    return this.getJson<JourneyResponse>(`/api/v1/journey?${params}`);
  }

  getJourneyStatus(userId: string) {
    const params = new URLSearchParams({ userId });
    return this.getJson<JourneyStatusResponse>(
      `/api/v1/journey/status?${params}`,
    );
  }
}

export const journeyRepository = new HttpJourneyRepository();

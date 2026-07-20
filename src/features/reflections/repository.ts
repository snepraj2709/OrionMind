import { apiRequest, type ApiRequest } from '@/services/api-client';

import {
  reflectionApiResponseSchema,
  type ReflectionApiResponse,
  type ReflectionRequest,
} from './api-schema';
import type { JournalEntry } from './model';

export interface ReflectionJournalService {
  getJournalEntries(): Promise<JournalEntry[]>;
}

export interface ReflectionsRepository {
  getReflection(input: ReflectionRequest): Promise<ReflectionApiResponse>;
}

export class HttpReflectionsRepository implements ReflectionsRepository {
  constructor(private readonly request: ApiRequest = apiRequest) {}

  async getReflection(input: ReflectionRequest) {
    const params = new URLSearchParams(input);
    const response = await this.request(`/api/v1/reflection?${params}`);
    if (!response.ok) {
      throw new Error(`Reflection request failed: ${response.status}`);
    }

    return reflectionApiResponseSchema.parse(await response.json());
  }
}

export const reflectionsRepository = new HttpReflectionsRepository();

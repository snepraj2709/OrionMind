import { apiRequest, type ApiRequest } from '@/services/api-client';

import {
  reflectionApiResponseSchema,
  reflectionFeedbackRequestSchema,
  reflectionFeedbackResultSchema,
  type ReflectionApiResponse,
  type ReflectionFeedbackResponse,
  type ReflectionFeedbackResult,
  type ReflectionRequest,
} from './api-schema';

export interface PutReflectionFeedbackInput {
  snapshotId: string;
  insightId: string;
  response: ReflectionFeedbackResponse;
}

export interface ReflectionsRepository {
  getReflection(input: ReflectionRequest): Promise<ReflectionApiResponse>;
  putFeedback(
    input: PutReflectionFeedbackInput,
  ): Promise<ReflectionFeedbackResult>;
}

export class HttpReflectionsRepository implements ReflectionsRepository {
  constructor(private readonly request: ApiRequest = apiRequest) {}

  async getReflection(input: ReflectionRequest) {
    const params = new URLSearchParams({ range: input.range });
    const response = await this.request(`/api/v1/reflections?${params}`);
    if (!response.ok) {
      throw new Error(`Reflection request failed: ${response.status}`);
    }

    return reflectionApiResponseSchema.parse(await response.json());
  }

  async putFeedback(input: PutReflectionFeedbackInput) {
    const body = reflectionFeedbackRequestSchema.parse({
      response: input.response,
    });
    const response = await this.request(
      `/api/v1/reflections/${encodeURIComponent(input.snapshotId)}/insights/${encodeURIComponent(input.insightId)}/feedback`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    );
    if (!response.ok) {
      throw new Error(`Reflection feedback failed: ${response.status}`);
    }

    return reflectionFeedbackResultSchema.parse(await response.json());
  }
}

export const reflectionsRepository = new HttpReflectionsRepository();

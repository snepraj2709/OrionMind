import { apiRequest, type ApiRequest } from '@/services/api-client';

import {
  reflectionApiResponseSchema,
  reflectionFeedbackRequestSchema,
  reflectionFeedbackResultSchema,
  reflectionRecalculationResultSchema,
  type ReflectionApiResponse,
  type ReflectionFeedbackResponse,
  type ReflectionFeedbackResult,
  type ReflectionRecalculationResult,
  type ReflectionRequest,
} from './api-schema';

export interface PutReflectionFeedbackInput {
  snapshotId: string;
  insightId: string;
  response: ReflectionFeedbackResponse;
}

export interface ReflectionsRepository {
  getReflection(
    input: ReflectionRequest,
    signal?: AbortSignal,
  ): Promise<ReflectionApiResponse>;
  recalculate(signal?: AbortSignal): Promise<ReflectionRecalculationResult>;
  putFeedback(
    input: PutReflectionFeedbackInput,
  ): Promise<ReflectionFeedbackResult>;
}

export class ReflectionRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly errorCode?: string,
  ) {
    super(message);
    this.name = 'ReflectionRequestError';
  }
}

async function requireOk(response: Response, operation: string) {
  if (!response.ok) {
    let errorCode: string | undefined;
    try {
      const body: unknown = await response.json();
      if (
        typeof body === 'object' &&
        body !== null &&
        'error_code' in body &&
        typeof body.error_code === 'string'
      ) {
        errorCode = body.error_code;
      }
    } catch {
      // Error envelopes are best-effort; status remains the safe fallback.
    }
    throw new ReflectionRequestError(
      `${operation} request failed: ${response.status}`,
      response.status,
      errorCode,
    );
  }
  return response;
}

export class HttpReflectionsRepository implements ReflectionsRepository {
  constructor(private readonly request: ApiRequest = apiRequest) {}

  async getReflection(input: ReflectionRequest, signal?: AbortSignal) {
    const params = new URLSearchParams({ range: input.range });
    const response = await requireOk(
      await this.request(`/api/v1/reflections?${params}`, { signal }),
      'Reflection',
    );

    return reflectionApiResponseSchema.parse(await response.json());
  }

  async recalculate(signal?: AbortSignal) {
    const response = await this.request('/api/v1/reflections/recalculate', {
      method: 'POST',
      signal,
    });
    await requireOk(response, 'Reflection recalculation');
    if (response.status !== 202) {
      throw new ReflectionRequestError(
        `Reflection recalculation request returned unexpected status: ${response.status}`,
        response.status,
      );
    }

    return reflectionRecalculationResultSchema.parse(await response.json());
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
    await requireOk(response, 'Reflection feedback');

    return reflectionFeedbackResultSchema.parse(await response.json());
  }
}

export const reflectionsRepository = new HttpReflectionsRepository();

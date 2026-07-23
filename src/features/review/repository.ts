import { apiRequest, type ApiRequest } from '@/services/api-client';

import {
  feedbackRequestSchemaForScope,
  reviewItemSchema,
  reviewItemsResponseSchema,
  reviewListQuerySchema,
} from './api-schema';
import type {
  ReviewFeedbackRequest,
  ReviewItem,
  ReviewItemsResponse,
  ReviewListQuery,
  ReviewScope,
} from './model';

export interface SubmitReviewFeedbackInput {
  itemId: string;
  scope: ReviewScope;
  feedback: ReviewFeedbackRequest;
}

export interface ReviewRepository {
  listItems(
    query: ReviewListQuery,
    signal?: AbortSignal,
  ): Promise<ReviewItemsResponse>;
  submitFeedback(
    input: SubmitReviewFeedbackInput,
    signal?: AbortSignal,
  ): Promise<ReviewItem>;
}

export class ReviewRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly errorCode?: string,
  ) {
    super(message);
    this.name = 'ReviewRequestError';
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
    throw new ReviewRequestError(
      `${operation} request failed: ${response.status}`,
      response.status,
      errorCode,
    );
  }
  return response;
}

export class HttpReviewRepository implements ReviewRepository {
  constructor(private readonly request: ApiRequest = apiRequest) {}

  async listItems(query: ReviewListQuery, signal?: AbortSignal) {
    const parsed = reviewListQuerySchema.parse(query);
    const params = new URLSearchParams({
      scope: parsed.scope,
      category: parsed.category,
      status: parsed.status,
      page: String(parsed.page),
      page_size: String(parsed.page_size),
    });
    const response = await requireOk(
      await this.request(`/api/v1/review/items?${params}`, { signal }),
      'Review list',
    );

    return reviewItemsResponseSchema.parse(await response.json());
  }

  async submitFeedback(input: SubmitReviewFeedbackInput, signal?: AbortSignal) {
    const body = feedbackRequestSchemaForScope(input.scope).parse(
      input.feedback,
    );
    const response = await requireOk(
      await this.request(
        `/api/v1/review/items/${encodeURIComponent(input.itemId)}/feedback`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal,
        },
      ),
      'Review feedback',
    );

    return reviewItemSchema.parse(await response.json());
  }
}

export const reviewRepository = new HttpReviewRepository();

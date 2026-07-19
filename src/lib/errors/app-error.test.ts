import { describe, expect, it } from 'vitest';

import { AppError, normalizeError } from './app-error';

describe('normalizeError', () => {
  it('preserves an existing AppError', () => {
    const error = new AppError('Try again later.', {
      code: 'dependency_unavailable',
      retryable: true,
      status: 503,
    });

    expect(normalizeError(error)).toBe(error);
  });

  it('normalizes unknown values without exposing their contents', () => {
    const error = normalizeError({ privateJournalText: 'sensitive' });

    expect(error).toMatchObject({
      code: 'unknown',
      message: 'An unexpected error occurred.',
      retryable: false,
    });
  });
});

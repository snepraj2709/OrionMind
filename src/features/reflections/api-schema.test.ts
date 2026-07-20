import { describe, expect, it } from 'vitest';

import {
  reflectionApiResponseSchema,
  reflectionRequestSchema,
  type ReflectionTab,
} from './api-schema';
import { reflectionEntryFixtures } from './fixtures';
import { buildReflectionApiResponse } from './response-builder';

const tabs: ReflectionTab[] = [
  'all',
  'hiddenDriver',
  'recurringLoop',
  'innerTension',
];

describe('reflection wire schemas', () => {
  it.each(tabs)('parses the %s response variant', (reflectionTab) => {
    const response = buildReflectionApiResponse({
      entries: reflectionEntryFixtures,
      range: 'all',
      reflectionTab,
      totalAvailable: reflectionEntryFixtures.length,
      userId: 'reader-id',
    });

    expect(reflectionApiResponseSchema.parse(response)).toEqual(response);
  });

  it('requires every request parameter and exact enum casing', () => {
    expect(
      reflectionRequestSchema.safeParse({
        userId: 'reader-id',
        reflectionTab: 'hiddenDriver',
        range: '30d',
      }).success,
    ).toBe(true);
    expect(
      reflectionRequestSchema.safeParse({
        userId: 'reader-id',
        reflectionTab: 'All',
        range: '30d',
      }).success,
    ).toBe(false);
    expect(
      reflectionRequestSchema.safeParse({
        userId: 'reader-id',
        reflectionTab: 'hiddenDriver',
      }).success,
    ).toBe(false);
  });

  it('rejects a malformed tab payload', () => {
    const malformed = buildReflectionApiResponse({
      entries: reflectionEntryFixtures,
      range: 'all',
      reflectionTab: 'hiddenDriver',
      totalAvailable: reflectionEntryFixtures.length,
      userId: 'reader-id',
    });

    expect(
      reflectionApiResponseSchema.safeParse({
        ...malformed,
        data: { statement: 'Incomplete hidden driver' },
      }).success,
    ).toBe(false);
  });
});

import { describe, expect, it } from 'vitest';

import {
  entriesApiFixtures,
  entriesApiResponseSchema,
  entriesRequestSchema,
} from '.';

describe('Entries API schemas', () => {
  it('parses the supported request and response contract', () => {
    expect(
      entriesRequestSchema.parse({
        page: '1',
        page_size: '20',
      }),
    ).toEqual({
      page: 1,
      page_size: 20,
    });

    expect(
      entriesApiResponseSchema.parse({
        items: entriesApiFixtures,
        page: 1,
        page_size: 20,
        total: entriesApiFixtures.length,
      }).items,
    ).toHaveLength(5);
  });

  it('rejects invalid pagination and malformed wire records', () => {
    expect(
      entriesRequestSchema.safeParse({ page: 0, page_size: 20 }).success,
    ).toBe(false);
    expect(
      entriesRequestSchema.safeParse({ page: 1, page_size: 101 }).success,
    ).toBe(false);
    expect(
      entriesApiResponseSchema.safeParse({
        items: [{ ...entriesApiFixtures[0], entry_date: '10 July 2025' }],
        page: 1,
        page_size: 20,
        total: 1,
      }).success,
    ).toBe(false);
  });
});

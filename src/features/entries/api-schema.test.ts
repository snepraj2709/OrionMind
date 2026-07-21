import { describe, expect, it } from 'vitest';

import {
  entriesApiFixtures,
  entriesApiResponseSchema,
  entriesRequestSchema,
  entryDetailApiResponseSchema,
} from '.';

const detailResponse = {
  id: '8a7cc7df-94e5-41b4-b983-ab6ddda47785',
  content: 'Entry content',
  input_type: 'audio',
  entry_date: '2026-07-21',
  original_theme_config_id: '046870f3-a50f-4406-a9d8-36e774a793f1',
  processing_status: 'pending',
  processing_error_code: null,
  created_at: '2026-07-21T10:00:00Z',
  classification: null,
  ideas: [],
  extracted_memories: [],
  reflections: [],
};

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

  it.each(['pending', 'processing', 'completed', 'failed'] as const)(
    'accepts the %s detail processing status',
    (processingStatus) => {
      expect(
        entryDetailApiResponseSchema.parse({
          ...detailResponse,
          processing_status: processingStatus,
        }),
      ).toMatchObject({
        input_type: 'audio',
        processing_status: processingStatus,
        classification: null,
      });
    },
  );

  it('rejects malformed detail records', () => {
    expect(
      entryDetailApiResponseSchema.safeParse({
        ...detailResponse,
        entry_date: '21 July 2026',
      }).success,
    ).toBe(false);
    expect(
      entryDetailApiResponseSchema.safeParse({
        ...detailResponse,
        reflections: [{ id: 'missing-fields' }],
      }).success,
    ).toBe(false);
  });
});

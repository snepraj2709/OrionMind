import { describe, expect, it, vi } from 'vitest';

import type { ApiRequest } from '@/services/api-client';

import { entriesApiFixtures } from './fixtures';
import { HttpEntriesRepository } from './repository';
import { buildEntriesApiResponse } from './response-builder';

describe('HttpEntriesRepository', () => {
  it('sends pagination and optional filters without a GET body', async () => {
    const request = vi.fn<ApiRequest>().mockResolvedValue(
      Response.json(
        buildEntriesApiResponse({
          entries: entriesApiFixtures,
          page: 2,
          page_size: 10,
          processing_status: 'processing',
          search: 'canal',
        }),
      ),
    );
    const repository = new HttpEntriesRepository(request);

    await repository.listEntries({
      pageIndex: 1,
      pageSize: 10,
      search: ' canal ',
      status: 'processing',
    });

    const [requestPath, requestInit] = request.mock.calls[0] ?? [];
    const requestUrl = new URL(String(requestPath), 'http://localhost');
    expect(requestUrl.pathname).toBe('/api/v1/entries');
    expect(Object.fromEntries(requestUrl.searchParams)).toEqual({
      page: '2',
      page_size: '10',
      processing_status: 'processing',
      search: 'canal',
    });
    expect(requestInit).toBeUndefined();
  });

  it('maps the wire response into the existing entry summary model', async () => {
    const request = vi.fn<ApiRequest>().mockResolvedValue(
      Response.json({
        items: [entriesApiFixtures[0]],
        page: 1,
        page_size: 10,
        total: 1,
        total_all: 5,
      }),
    );

    const result = await new HttpEntriesRepository(request).listEntries({
      pageIndex: 0,
      pageSize: 10,
      search: '',
      status: 'all',
    });

    expect(result).toMatchObject({
      page: 1,
      pageSize: 10,
      total: 1,
      totalAll: 5,
    });
    expect(result.items[0]).toMatchObject({
      content: entriesApiFixtures[0]?.content_preview,
      date: entriesApiFixtures[0]?.entry_date,
      inputType: entriesApiFixtures[0]?.input_type,
      status: entriesApiFixtures[0]?.processing_status,
      themes: ['personalGrowth', 'health', 'familyAndFriends'],
    });
  });

  it('rejects failed, malformed, and unsupported responses', async () => {
    const request = vi
      .fn<ApiRequest>()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(Response.json({ items: [] }))
      .mockResolvedValueOnce(
        Response.json({
          items: [{ ...entriesApiFixtures[0], processing_status: 'queued' }],
          page: 1,
          page_size: 10,
          total: 1,
          total_all: 1,
        }),
      );
    const repository = new HttpEntriesRepository(request);
    const input = {
      pageIndex: 0,
      pageSize: 10,
      search: '',
      status: 'all',
    } as const;

    await expect(repository.listEntries(input)).rejects.toThrow(
      'Entries request failed: 401',
    );
    await expect(repository.listEntries(input)).rejects.toThrow();
    await expect(repository.listEntries(input)).rejects.toThrow(
      'Unsupported entry processing status: queued',
    );
  });
});

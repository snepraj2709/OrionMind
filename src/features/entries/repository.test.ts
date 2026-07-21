import { describe, expect, it, vi } from 'vitest';

import type { ApiRequest } from '@/services/api-client';

import { entriesApiFixtures } from './fixtures';
import { HttpEntriesRepository } from './repository';

const createdEntryResponse = {
  id: '8a7cc7df-94e5-41b4-b983-ab6ddda47785',
  content: 'A newly created entry.',
  input_type: 'audio' as const,
  entry_date: '2026-07-21',
  processing_status: 'pending' as const,
  classification: {
    themes: [
      {
        key: 'personal_growth',
        name: 'Personal Growth',
        score: 0.9,
        tier: 'primary' as const,
      },
    ],
  },
};

describe('HttpEntriesRepository', () => {
  it('sends only the backend-supported pagination parameters', async () => {
    const request = vi.fn<ApiRequest>().mockResolvedValue(
      Response.json({
        items: entriesApiFixtures,
        page: 2,
        page_size: 10,
        total: entriesApiFixtures.length,
      }),
    );
    const repository = new HttpEntriesRepository(request);

    await repository.listEntries({ pageIndex: 1, pageSize: 10 });

    const [requestPath, requestInit] = request.mock.calls[0] ?? [];
    const requestUrl = new URL(String(requestPath), 'http://localhost');
    expect(requestUrl.pathname).toBe('/api/v1/entries');
    expect(Object.fromEntries(requestUrl.searchParams)).toEqual({
      page: '2',
      page_size: '10',
    });
    expect(requestInit).toBeUndefined();
  });

  it('maps audio, snake-case themes, date-only dates, and pending status', async () => {
    const audioItem = {
      ...entriesApiFixtures[0],
      input_type: 'audio' as const,
      processing_status: 'pending' as const,
    };
    const request = vi
      .fn<ApiRequest>()
      .mockResolvedValue(
        Response.json({ items: [audioItem], page: 1, page_size: 10, total: 1 }),
      );

    const result = await new HttpEntriesRepository(request).listEntries({
      pageIndex: 0,
      pageSize: 10,
    });

    expect(result).toMatchObject({ page: 1, pageSize: 10, total: 1 });
    expect(result.items[0]).toMatchObject({
      date: audioItem.entry_date,
      inputType: 'voice',
      status: 'pending',
      themes: ['personalGrowth', 'health', 'familyAndFriends'],
    });
  });

  it('uses the exact draft methods and JSON body', async () => {
    const request = vi
      .fn<ApiRequest>()
      .mockResolvedValueOnce(
        Response.json({ content: 'restored', updated_at: null }),
      )
      .mockResolvedValueOnce(
        Response.json({
          content: 'saved',
          updated_at: '2026-07-21T10:00:00Z',
        }),
      )
      .mockResolvedValueOnce(
        Response.json({ content: null, updated_at: null }),
      );
    const repository = new HttpEntriesRepository(request);

    await expect(repository.getTextDraft()).resolves.toEqual({
      content: 'restored',
      updatedAt: null,
    });
    await repository.saveTextDraft('saved');
    await repository.discardTextDraft();

    expect(request.mock.calls).toEqual([
      ['/api/v1/entry/draft'],
      [
        '/api/v1/entry/draft',
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: 'saved' }),
        },
      ],
      ['/api/v1/entry/draft', { method: 'DELETE' }],
    ]);
  });

  it('posts only canonical text content without an idempotency header', async () => {
    const request = vi
      .fn<ApiRequest>()
      .mockResolvedValue(
        Response.json({ ...createdEntryResponse, input_type: 'text' }),
      );
    const repository = new HttpEntriesRepository(request);

    const result = await repository.createTextEntry({ content: 'canonical' });

    expect(request).toHaveBeenCalledWith('/api/v1/entry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: 'canonical' }),
    });
    expect(result).toMatchObject({ inputType: 'text', status: 'pending' });
    expect(
      Object.keys(JSON.parse(request.mock.calls[0]?.[1]?.body as string)),
    ).toEqual(['content']);
  });

  it('normalizes voice MIME, uses audio multipart, and preserves the supplied key', async () => {
    const request = vi
      .fn<ApiRequest>()
      .mockResolvedValue(Response.json(createdEntryResponse));
    const repository = new HttpEntriesRepository(request);

    const result = await repository.createVoiceEntry({
      idempotencyKey: 'stable-recording-key',
      recording: new Blob(['voice'], { type: 'audio/webm;codecs=opus' }),
    });

    const [path, init] = request.mock.calls[0] ?? [];
    expect(path).toBe('/api/v1/entries/voice');
    expect(init?.method).toBe('POST');
    expect(init?.headers).toEqual({
      'Idempotency-Key': 'stable-recording-key',
    });
    expect(new Headers(init?.headers).has('Content-Type')).toBe(false);
    expect(init?.body).toBeInstanceOf(FormData);
    const audio = (init?.body as FormData).get('audio');
    expect(audio).toBeInstanceOf(Blob);
    expect((audio as Blob).type).toBe('audio/webm');
    expect(result).toMatchObject({ inputType: 'voice', status: 'pending' });
  });

  it('rejects empty, oversized, unsupported, non-2xx, and malformed responses safely', async () => {
    const repository = new HttpEntriesRepository(vi.fn<ApiRequest>());
    await expect(
      repository.createVoiceEntry({
        idempotencyKey: 'key',
        recording: new Blob([], { type: 'audio/webm' }),
      }),
    ).rejects.toThrow('empty');
    await expect(
      repository.createVoiceEntry({
        idempotencyKey: 'key',
        recording: new Blob([new Uint8Array(25 * 1024 * 1024 + 1)], {
          type: 'audio/webm',
        }),
      }),
    ).rejects.toMatchObject({ status: 413 });
    await expect(
      repository.createVoiceEntry({
        idempotencyKey: 'key',
        recording: new Blob(['voice'], { type: 'audio/aac' }),
      }),
    ).rejects.toMatchObject({ status: 415 });

    const failingRequest = vi
      .fn<ApiRequest>()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(Response.json({ items: [] }));
    const failingRepository = new HttpEntriesRepository(failingRequest);
    await expect(failingRepository.getTextDraft()).rejects.toMatchObject({
      status: 503,
    });
    await expect(
      failingRepository.listEntries({ pageIndex: 0, pageSize: 10 }),
    ).rejects.toThrow();
  });
});

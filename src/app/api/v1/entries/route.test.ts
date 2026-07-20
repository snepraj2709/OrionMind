import { beforeEach, describe, expect, it, vi } from 'vitest';

import { entriesApiResponseSchema } from '@/features/entries';

import { GET } from './route';

const authMocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
}));

vi.mock('@/services/auth', () => ({
  getCurrentUser: authMocks.getCurrentUser,
}));

const user = { id: 'reader-id', email: 'reader@example.com', name: 'Reader' };

function request(params: Record<string, string>) {
  return new Request(
    `http://localhost/api/v1/entries?${new URLSearchParams(params)}`,
  );
}

beforeEach(() => {
  authMocks.getCurrentUser.mockReset();
  authMocks.getCurrentUser.mockResolvedValue(user);
});

describe('GET /api/v1/entries', () => {
  it('returns the authenticated, newest-first paginated list', async () => {
    const response = await GET(request({ page: '2', page_size: '2' }));
    const body = entriesApiResponseSchema.parse(await response.json());

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      page: 2,
      page_size: 2,
      total: 5,
      total_all: 5,
    });
    expect(body.items.map((item) => item.id)).toEqual(['e3', 'e4']);
  });

  it('applies search and status before pagination', async () => {
    const searched = entriesApiResponseSchema.parse(
      await (
        await GET(request({ page: '1', page_size: '10', search: 'canal' }))
      ).json(),
    );
    const filtered = entriesApiResponseSchema.parse(
      await (
        await GET(
          request({
            page: '1',
            page_size: '10',
            processing_status: 'completed',
          }),
        )
      ).json(),
    );

    expect(searched.items.map((item) => item.id)).toEqual(['e4']);
    expect(searched).toMatchObject({ total: 1, total_all: 5 });
    expect(filtered.items.map((item) => item.id)).toEqual(['e1', 'e2', 'e3']);
    expect(filtered).toMatchObject({ total: 3, total_all: 5 });
  });

  it('returns a valid empty page without changing its totals', async () => {
    const body = entriesApiResponseSchema.parse(
      await (await GET(request({ page: '4', page_size: '2' }))).json(),
    );

    expect(body.items).toEqual([]);
    expect(body).toMatchObject({ page: 4, total: 5, total_all: 5 });
  });

  it('enforces authentication and validates query parameters', async () => {
    authMocks.getCurrentUser.mockResolvedValueOnce(null);
    expect((await GET(request({ page: '1', page_size: '10' }))).status).toBe(
      401,
    );

    expect((await GET(request({ page_size: '10' }))).status).toBe(400);
    expect((await GET(request({ page: '0', page_size: '10' }))).status).toBe(
      400,
    );
    expect((await GET(request({ page: '1', page_size: '101' }))).status).toBe(
      400,
    );
    expect(
      (
        await GET(
          request({
            page: '1',
            page_size: '10',
            processing_status: 'queued',
          }),
        )
      ).status,
    ).toBe(400);
  });
});

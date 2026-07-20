import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  reflectionApiResponseSchema,
  reflectionCopyFixture,
  type ReflectionRange,
  type ReflectionTab,
} from '@/features/reflections';

import { GET } from './route';

const authMocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
}));

vi.mock('@/services/auth', () => ({
  getCurrentUser: authMocks.getCurrentUser,
}));

const user = { id: 'reader-id', email: 'reader@example.com', name: 'Reader' };
const tabs: ReflectionTab[] = [
  'all',
  'hiddenDriver',
  'recurringLoop',
  'innerTension',
];
const expectedEntryCounts: Record<ReflectionRange, number> = {
  '7d': 3,
  '30d': 8,
  all: 8,
};

function request(reflectionTab: string, range: string, userId = user.id) {
  const params = new URLSearchParams({ reflectionTab, range, userId });
  return new Request(`http://localhost/api/v1/reflection?${params}`);
}

beforeEach(() => {
  authMocks.getCurrentUser.mockReset();
  authMocks.getCurrentUser.mockResolvedValue(user);
});

describe('GET /api/v1/reflection', () => {
  it.each(tabs)('returns a valid direct %s payload', async (reflectionTab) => {
    const response = await GET(request(reflectionTab, 'all'));
    const body: unknown = await response.json();

    expect(response.status).toBe(200);
    expect(() => reflectionApiResponseSchema.parse(body)).not.toThrow();
    expect(body).toMatchObject({
      userId: user.id,
      reflectionTab,
      range: 'all',
      period: {
        entryCount: 8,
        totalAvailable: 8,
        from: '2025-04-14',
        to: '2025-05-08',
      },
    });
  });

  it.each(Object.entries(expectedEntryCounts))(
    'filters the %s range to %i entries',
    async (range, entryCount) => {
      const response = await GET(request('hiddenDriver', range));
      const body = reflectionApiResponseSchema.parse(await response.json());

      expect(body.period.entryCount).toBe(entryCount);
      expect(body.period.totalAvailable).toBe(8);
      if (body.reflectionTab === 'hiddenDriver') {
        expect(body.data.observedEntryCount).toBe(entryCount);
      }
    },
  );

  it('returns all datasets only for the All variant', async () => {
    const all = reflectionApiResponseSchema.parse(
      await (await GET(request('all', 'all'))).json(),
    );
    expect(all.reflectionTab).toBe('all');
    if (all.reflectionTab !== 'all') return;
    expect(all.data.hiddenDriver.statement).toBe(
      reflectionCopyFixture.hiddenDriver.statement,
    );
    expect(all.data.recurringLoop.steps).toHaveLength(6);
    expect(all.data.innerTension.title).toBe(
      reflectionCopyFixture.innerTension.title,
    );

    const hidden = reflectionApiResponseSchema.parse(
      await (await GET(request('hiddenDriver', 'all'))).json(),
    );
    expect(hidden.reflectionTab).toBe('hiddenDriver');
    if (hidden.reflectionTab !== 'hiddenDriver') return;
    expect(hidden.data).not.toHaveProperty('recurringLoop');
    expect(hidden.data).not.toHaveProperty('innerTension');
  });

  it('limits every All-variant evidence collection to the selected range', async () => {
    const body = reflectionApiResponseSchema.parse(
      await (await GET(request('all', '7d'))).json(),
    );
    expect(body.reflectionTab).toBe('all');
    if (body.reflectionTab !== 'all') return;

    const evidenceDates = [
      ...body.data.hiddenDriver.evidence,
      ...body.data.recurringLoop.evidence,
      ...body.data.recurringLoop.steps.flatMap((step) => step.evidence),
      ...body.data.innerTension.tensions.flatMap((tension) => tension.evidence),
    ].map((item) => item.date);

    expect(evidenceDates.length).toBeGreaterThan(0);
    expect(evidenceDates.every((date) => date >= '2025-05-02')).toBe(true);
  });

  it('enforces authentication, required values, exact enums, and ownership', async () => {
    authMocks.getCurrentUser.mockResolvedValueOnce(null);
    expect((await GET(request('hiddenDriver', 'all'))).status).toBe(401);

    expect(
      (
        await GET(
          new Request(
            'http://localhost/api/v1/reflection?reflectionTab=hiddenDriver&range=all',
          ),
        )
      ).status,
    ).toBe(400);
    expect((await GET(request('hiddenDriver', 'week'))).status).toBe(400);
    expect((await GET(request('All', 'all'))).status).toBe(400);
    expect(
      (await GET(request('hiddenDriver', 'all', 'another-reader'))).status,
    ).toBe(403);
  });
});

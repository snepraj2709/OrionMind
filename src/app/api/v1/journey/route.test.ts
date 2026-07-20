import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  JOURNEY_RANGES,
  journeyStreamForRange,
  type JourneyRange,
} from '@/features/journey';

import { GET as getJourney } from './route';
import { GET as getJourneyStatus } from './status/route';

const authMocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
}));

vi.mock('@/services/auth', () => ({
  getCurrentUser: authMocks.getCurrentUser,
}));

const user = { id: 'reader-id', email: 'reader@example.com', name: 'Reader' };
const expectedEntryCounts: Record<JourneyRange, number> = {
  '6m': 6,
  '1y': 12,
  '2y': 24,
  '3y': 30,
  '5y': 30,
  all: 30,
};

function request(path: string) {
  return new Request(`http://localhost${path}`);
}

beforeEach(() => {
  authMocks.getCurrentUser.mockReset();
  authMocks.getCurrentUser.mockResolvedValue(user);
});

describe('GET /api/v1/journey', () => {
  it.each(JOURNEY_RANGES)(
    'returns typed fixture data for %s',
    async (range) => {
      const response = await getJourney(
        request(`/api/v1/journey?range=${range}&userId=${user.id}`),
      );
      const body = await response.json();

      expect(response.status).toBe(200);
      expect(body).toMatchObject({
        range,
        totalAvailable: 30,
        stream: expect.arrayContaining([
          expect.objectContaining({ label: expect.any(String) }),
        ]),
      });
      expect(body.entries).toHaveLength(expectedEntryCounts[range]);
      expect(body.stream).toEqual(journeyStreamForRange(range));
    },
  );

  it('validates authentication, user ownership, and range', async () => {
    authMocks.getCurrentUser.mockResolvedValueOnce(null);
    expect(
      (await getJourney(request('/api/v1/journey?range=all&userId=reader-id')))
        .status,
    ).toBe(401);

    expect(
      (await getJourney(request('/api/v1/journey?range=all'))).status,
    ).toBe(400);
    expect(
      (await getJourney(request('/api/v1/journey?userId=reader-id'))).status,
    ).toBe(400);
    expect(
      (
        await getJourney(
          request('/api/v1/journey?range=all&userId=another-reader'),
        )
      ).status,
    ).toBe(403);
    expect(
      (await getJourney(request('/api/v1/journey?range=week&userId=reader-id')))
        .status,
    ).toBe(400);
  });
});

describe('GET /api/v1/journey/status', () => {
  it('returns the exact locked fixture', async () => {
    const response = await getJourneyStatus(
      request(`/api/v1/journey/status?userId=${user.id}`),
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      enabled: false,
      daysSinceSignup: 18,
      entriesAdded: 9,
    });
  });

  it('uses the same authentication and ownership boundary', async () => {
    authMocks.getCurrentUser.mockResolvedValueOnce(null);
    expect(
      (
        await getJourneyStatus(
          request('/api/v1/journey/status?userId=reader-id'),
        )
      ).status,
    ).toBe(401);
    expect(
      (await getJourneyStatus(request('/api/v1/journey/status'))).status,
    ).toBe(400);
    expect(
      (
        await getJourneyStatus(
          request('/api/v1/journey/status?userId=another-reader'),
        )
      ).status,
    ).toBe(403);
  });
});

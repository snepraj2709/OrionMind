import {
  journeyEntriesForRange,
  journeyEntryFixtures,
  journeyStreamForRange,
} from '@/features/journey/fixtures';

import { validateJourneyApiRequest } from './request';

export async function GET(request: Request) {
  const validation = await validateJourneyApiRequest(request, {
    requireRange: true,
  });
  if (!validation.ok) return validation.response;

  const range = validation.range!;
  return Response.json({
    entries: journeyEntriesForRange(journeyEntryFixtures, range),
    range,
    stream: journeyStreamForRange(range),
    totalAvailable: journeyEntryFixtures.length,
  });
}

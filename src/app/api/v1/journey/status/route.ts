import { journeyStatusFixture } from '@/features/journey/fixtures';

import { validateJourneyApiRequest } from '../request';

export async function GET(request: Request) {
  const validation = await validateJourneyApiRequest(request, {
    requireRange: false,
  });
  if (!validation.ok) return validation.response;

  return Response.json(journeyStatusFixture);
}

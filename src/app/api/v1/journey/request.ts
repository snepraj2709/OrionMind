import { JOURNEY_RANGES } from '@/features/journey/constants';
import type { JourneyRange } from '@/features/journey/model';
import { getCurrentUser } from '@/services/auth';

type JourneyApiValidation =
  | { ok: true; userId: string; range?: JourneyRange }
  | { ok: false; response: Response };

function errorResponse(error: string, status: number) {
  return Response.json({ error }, { status });
}

export async function validateJourneyApiRequest(
  request: Request,
  options: { requireRange: boolean },
): Promise<JourneyApiValidation> {
  const user = await getCurrentUser();
  if (!user) {
    return { ok: false, response: errorResponse('Unauthorized', 401) };
  }

  const searchParams = new URL(request.url).searchParams;
  const userId = searchParams.get('userId');
  if (!userId) {
    return {
      ok: false,
      response: errorResponse('userId is required', 400),
    };
  }
  if (userId !== user.id) {
    return {
      ok: false,
      response: errorResponse('Forbidden', 403),
    };
  }

  if (!options.requireRange) return { ok: true, userId };

  const range = searchParams.get('range');
  if (!range || !JOURNEY_RANGES.includes(range as JourneyRange)) {
    return {
      ok: false,
      response: errorResponse('A valid range is required', 400),
    };
  }

  return { ok: true, range: range as JourneyRange, userId };
}

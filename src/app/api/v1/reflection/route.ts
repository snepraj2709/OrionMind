import {
  buildReflectionApiResponse,
  reflectionEntryFixtures,
  reflectionRequestSchema,
} from '@/features/reflections';
import { getCurrentUser } from '@/services/auth';

function errorResponse(error: string, status: number) {
  return Response.json({ error }, { status });
}

export async function GET(request: Request) {
  const user = await getCurrentUser();
  if (!user) return errorResponse('Unauthorized', 401);

  const searchParams = new URL(request.url).searchParams;
  const validation = reflectionRequestSchema.safeParse({
    userId: searchParams.get('userId'),
    reflectionTab: searchParams.get('reflectionTab'),
    range: searchParams.get('range'),
  });
  if (!validation.success) {
    return errorResponse('Invalid reflection request', 400);
  }
  if (validation.data.userId !== user.id) {
    return errorResponse('Forbidden', 403);
  }

  return Response.json(
    buildReflectionApiResponse({
      ...validation.data,
      entries: reflectionEntryFixtures,
      totalAvailable: reflectionEntryFixtures.length,
    }),
  );
}

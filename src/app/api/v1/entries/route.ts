import {
  buildEntriesApiResponse,
  entriesApiFixtures,
  entriesRequestSchema,
} from '@/features/entries';
import { getCurrentUser } from '@/services/auth';

function errorResponse(error: string, status: number) {
  return Response.json({ error }, { status });
}

export async function GET(request: Request) {
  const user = await getCurrentUser();
  if (!user) return errorResponse('Unauthorized', 401);

  const searchParams = new URL(request.url).searchParams;
  const validation = entriesRequestSchema.safeParse({
    page: searchParams.get('page'),
    page_size: searchParams.get('page_size'),
  });
  if (!validation.success) {
    return errorResponse('Invalid entries request', 400);
  }

  return Response.json(
    buildEntriesApiResponse({
      ...validation.data,
      entries: entriesApiFixtures,
    }),
  );
}

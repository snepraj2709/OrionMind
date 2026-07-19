import { APP_NAME } from '@/constants/app';

export function GET() {
  return Response.json({
    name: APP_NAME,
    status: 'ok',
  });
}

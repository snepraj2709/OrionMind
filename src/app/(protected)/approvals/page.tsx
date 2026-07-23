import { redirect } from 'next/navigation';

import { routes } from '@/config/routes';

export default function ApprovalsPage() {
  redirect(routes.review.path);
}

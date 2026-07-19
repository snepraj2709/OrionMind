import { redirect } from 'next/navigation';

import { routes } from '@/config/routes';
import { getCurrentUser } from '@/services/auth';

export default async function HomePage() {
  const user = await getCurrentUser();
  redirect(user ? routes.entries.path : routes.login.path);
}

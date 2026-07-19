import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { IdeasScreen } from '@/features/ideas';

export const metadata: Metadata = { title: routes.ideas.label };

export default function IdeasPage() {
  return <IdeasScreen />;
}

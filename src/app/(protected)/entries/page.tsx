import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { EntriesScreen } from '@/features/entries';

export const metadata: Metadata = { title: routes.entries.label };

export default function EntriesPage() {
  return <EntriesScreen />;
}

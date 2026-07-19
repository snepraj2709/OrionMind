import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { NewEntryScreen } from '@/features/entries';

export const metadata: Metadata = { title: routes.newEntry.label };

export default function NewEntryPage() {
  return <NewEntryScreen />;
}

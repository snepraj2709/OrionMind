import type { Metadata } from 'next';

import { routes } from '@/config/routes';

import { EntriesPageContent } from './entries-page';

export const metadata: Metadata = { title: routes.entries.label };

export default function EntriesPage() {
  return <EntriesPageContent />;
}

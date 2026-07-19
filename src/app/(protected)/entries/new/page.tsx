import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.newEntry.label };

export default function NewEntryPage() {
  return (
    <RouteScaffold
      description="Capture a new journal entry in text or voice."
      title={routes.newEntry.label}
    />
  );
}

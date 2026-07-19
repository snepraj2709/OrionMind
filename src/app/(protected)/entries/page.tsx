import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.entries.label };

export default function EntriesPage() {
  return (
    <RouteScaffold
      description="Review journal entries and their processing state."
      title={routes.entries.label}
    />
  );
}

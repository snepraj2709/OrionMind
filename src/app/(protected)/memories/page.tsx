import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.memories.label };

export default function MemoriesPage() {
  return (
    <RouteScaffold
      description="Browse meaningful moments preserved from your writing."
      title={routes.memories.label}
    />
  );
}

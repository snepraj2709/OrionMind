import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.journey.label };

export default function JourneyPage() {
  return (
    <RouteScaffold
      description="Explore chapters, themes, and change across your writing."
      title={routes.journey.label}
    />
  );
}

import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.ideas.label };

export default function IdeasPage() {
  return (
    <RouteScaffold
      description="Return to ideas approved from your journal entries."
      title={routes.ideas.label}
    />
  );
}

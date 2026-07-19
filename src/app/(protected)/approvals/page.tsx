import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.approvals.label };

export default function ApprovalsPage() {
  return (
    <RouteScaffold
      description="Review ideas and memories before adding them to Orion."
      title={routes.approvals.label}
    />
  );
}

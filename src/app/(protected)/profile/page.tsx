import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.profile.label };

export default function ProfilePage() {
  return (
    <RouteScaffold
      description="Manage your identity and Orion preferences."
      title={routes.profile.label}
    />
  );
}

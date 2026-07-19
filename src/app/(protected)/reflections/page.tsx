import type { Metadata } from 'next';

import { RouteScaffold } from '@/components/shared';
import { routes } from '@/config/routes';

export const metadata: Metadata = { title: routes.reflections.label };

export default function ReflectionsPage() {
  return (
    <RouteScaffold
      description="Notice hidden drivers, recurring loops, and inner tensions."
      title={routes.reflections.label}
    />
  );
}

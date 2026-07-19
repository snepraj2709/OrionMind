import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { ReflectionsScreen } from '@/features/reflections';

export const metadata: Metadata = { title: routes.reflections.label };

export default function ReflectionsPage() {
  return <ReflectionsScreen />;
}

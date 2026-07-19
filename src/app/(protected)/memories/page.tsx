import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { MemoriesScreen } from '@/features/memories';

export const metadata: Metadata = { title: routes.memories.label };

export default function MemoriesPage() {
  return <MemoriesScreen />;
}

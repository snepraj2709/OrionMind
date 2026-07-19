import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { JourneyScreen } from '@/features/journey';

export const metadata: Metadata = { title: routes.journey.label };

export default function JourneyPage() {
  return <JourneyScreen />;
}

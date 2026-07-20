import type { Metadata } from 'next';

import { LandingPage } from '@/features/landing';

export const metadata: Metadata = {
  title: 'Connect the dots in your thoughts',
  description:
    'Record what is on your mind, notice what keeps returning and understand the patterns shaping your life with Orion.',
};

export default function HomePage() {
  return <LandingPage />;
}

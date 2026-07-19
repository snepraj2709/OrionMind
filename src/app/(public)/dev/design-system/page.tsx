import type { Metadata } from 'next';

import { DesignSystemCatalog } from './catalog';

export const metadata: Metadata = {
  title: 'Design System',
  robots: {
    index: false,
    follow: false,
  },
};

export default function DesignSystemPage() {
  return <DesignSystemCatalog />;
}

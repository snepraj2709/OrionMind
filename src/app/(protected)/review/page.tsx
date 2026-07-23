import type { Metadata } from 'next';

import { routes } from '@/config/routes';
import { ReviewScreen } from '@/features/review';

export const metadata: Metadata = { title: routes.review.label };

export default function ReviewPage() {
  return <ReviewScreen />;
}

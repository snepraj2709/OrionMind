'use client';

import { EntriesScreen } from '@/features/entries';
import { useAuth } from '@/features/auth';
import { usePendingReviewCount } from '@/features/review';

export function EntriesPageContent() {
  const { user } = useAuth();
  const { count, isError } = usePendingReviewCount(user?.id);

  return <EntriesScreen pendingReviewCount={isError ? null : count} />;
}

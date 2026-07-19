'use client';

import { usePendingApprovalCount } from '@/features/approvals';
import { EntriesScreen } from '@/features/entries';

export function EntriesPageContent() {
  const pendingReviewCount = usePendingApprovalCount();

  return <EntriesScreen pendingReviewCount={pendingReviewCount} />;
}

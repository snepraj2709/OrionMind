'use client';

import { AppNavigation } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';

import { usePendingApprovalCount } from './queries';

interface ReviewCountProps {
  initialCount: number;
}

export function ApprovalAwareNavigation({ initialCount }: ReviewCountProps) {
  const count = usePendingApprovalCount(initialCount);
  return <AppNavigation reviewCount={count} />;
}

export function ReviewQueueSummary({ initialCount }: ReviewCountProps) {
  const count = usePendingApprovalCount(initialCount);

  return (
    <AppLink
      aria-label={`${count} items to review`}
      className="type-body-small text-muted-foreground gap-2"
      href={routes.approvals.path}
    >
      <span
        aria-hidden="true"
        className="bg-status-warning radius-pill size-2"
      />
      {count} to review
    </AppLink>
  );
}

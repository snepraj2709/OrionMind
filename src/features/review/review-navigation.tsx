'use client';

import { AppNavigation } from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { routes } from '@/config/routes';
import { useAuth } from '@/features/auth';

import { usePendingReviewCount } from './queries';
import type { ReviewRepository } from './repository';

interface ReviewNavigationProps {
  repository?: ReviewRepository;
}

export function ReviewAwareNavigation({ repository }: ReviewNavigationProps) {
  const { user } = useAuth();
  const { count } = usePendingReviewCount(user?.id, repository);

  return <AppNavigation reviewCount={count ?? 0} />;
}

export function ReviewQueueSummary({ repository }: ReviewNavigationProps) {
  const { user } = useAuth();
  const { count } = usePendingReviewCount(user?.id, repository);
  const label =
    count === undefined
      ? 'Review queue'
      : `${count} ${count === 1 ? 'item' : 'items'} to review`;

  return (
    <AppLink
      aria-label={label}
      className="type-body-small text-muted-foreground gap-2"
      href={routes.review.path}
    >
      {count !== undefined && count > 0 ? (
        <span
          aria-hidden="true"
          className="bg-status-warning radius-pill size-2"
        />
      ) : null}
      {count === undefined ? 'Review' : `${count} to review`}
    </AppLink>
  );
}

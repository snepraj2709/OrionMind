import { AppButton, Typography } from '@/components/design-system';
import type { DataViewStatus as DataViewStatusValue } from '@/lib/query-state';

import { SkeletonList } from './loaders';
import { InlineError, PageErrorState } from './states';

interface DataViewErrorCopy {
  description: string;
  title: string;
}

export interface DataViewStatusProps {
  status: DataViewStatusValue;
  initialError: DataViewErrorCopy;
  onRetry: () => void;
  refreshError: string;
  refreshingAriaLabel?: string;
  refreshingLabel: string;
  retryDisabled?: boolean;
  skeletonCount?: number;
}

export function DataViewStatus({
  initialError,
  onRetry,
  refreshError,
  refreshingAriaLabel,
  refreshingLabel,
  retryDisabled = false,
  skeletonCount = 3,
  status,
}: DataViewStatusProps) {
  if (status === 'loading') return <SkeletonList count={skeletonCount} />;

  if (status === 'initial-error') {
    return (
      <PageErrorState
        action={
          <AppButton
            disabled={retryDisabled}
            onClick={onRetry}
            variant="secondary"
          >
            Retry
          </AppButton>
        }
        description={initialError.description}
        title={initialError.title}
      />
    );
  }

  if (status === 'refresh-error') {
    return (
      <InlineError
        action={
          <AppButton
            disabled={retryDisabled}
            onClick={onRetry}
            size="compact"
            variant="ghost"
          >
            Retry
          </AppButton>
        }
      >
        {refreshError}
      </InlineError>
    );
  }

  if (status === 'refreshing') {
    return (
      <Typography
        aria-label={refreshingAriaLabel ?? refreshingLabel}
        aria-live="polite"
        className="text-muted-foreground"
        role="status"
        variant="bodySmall"
      >
        {refreshingLabel}
      </Typography>
    );
  }

  return null;
}

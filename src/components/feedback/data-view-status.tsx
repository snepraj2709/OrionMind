import { AppButton } from '@/components/design-system';
import type { DataViewStatus as DataViewStatusValue } from '@/lib/query-state';

import { PageErrorState, PageLoadingState } from './states';

interface DataViewErrorCopy {
  description: string;
  title: string;
}

export interface DataViewStatusProps {
  status: DataViewStatusValue;
  initialError: DataViewErrorCopy;
  onRetry: () => void;
  refreshError: string;
  retryDisabled?: boolean;
}

export function DataViewStatus({
  initialError,
  onRetry,
  refreshError,
  retryDisabled = false,
  status,
}: DataViewStatusProps) {
  if (status === 'loading') return <PageLoadingState />;

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
        description={refreshError}
        title="Refresh failed"
      />
    );
  }

  if (status === 'refreshing') {
    return (
      <PageLoadingState
        description="Orion is checking for updates. Your current view will stay in place."
        title="Refreshing"
      />
    );
  }

  return null;
}

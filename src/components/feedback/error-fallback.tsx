'use client';

import { AppButton } from '@/components/design-system';
import { PageShell } from '@/components/layout';

import { PageErrorState } from './states';

interface ErrorFallbackProps {
  title: string;
  description: string;
  onRetry?: () => void;
}

export function ErrorFallback({
  title,
  description,
  onRetry,
}: ErrorFallbackProps) {
  return (
    <PageShell as="main" id="main-content">
      <PageErrorState
        action={
          onRetry ? (
            <AppButton onClick={onRetry}>Try again</AppButton>
          ) : undefined
        }
        description={description}
        title={title}
      />
    </PageShell>
  );
}
